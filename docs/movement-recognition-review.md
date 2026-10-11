# Movement recognition review

The recording gives us specific examples to correct before changing the recognizer. My recommendation is to test an interpretable combination of pose templates, short motion histories, and action state. The current failures do not yet establish a need for a trained gesture model.

## Review material

Open `../outputs/failure-review/movement-review.xlsx`. It contains 32 movement examples and six neutral intervals. `Action review` has my visual interpretation and the visible detector events. Yellow columns are for your ground truth, expected gestures, review status, and notes. `Frames` contains start, representative, and end images for each ID.

The labels are hypotheses about intent. Even when a physical movement is clear, I cannot know whether you intended a command, recovery, or repositioning. Review the motion examples before using them as test labels. An example correction is: A08, "Squat then stand", "CROUCH only", "Confirmed", "No jump intended".

Source: `../failurvid.mp4`, 3840 × 2160, 60 recorded frames/s, duration 140.968 seconds. Frame numbers are zero-based recording frames, not inference frames. Start/end boundaries are approximate annotations. The middle image is representative, not necessarily the maximum displacement. Overview samples cover the full recording every two seconds. Selected movement windows were additionally inspected at 0.25-second spacing, with 0.5-second contact sheets for some longer windows. Very brief movements can fall between samples. Audio was not transcribed. No new pose inference was run.

The detector log is cumulative and newest-first. A displayed big label can persist after an event. Observed sequences were inferred from newly appearing log entries, rather than counted from repeated labels. This is not a complete frame-by-frame event trace. The visible log establishes recognition, not successful swipe delivery or the game's interpretation. The source version that produced the video was not captured, so the checked-out code provides plausible explanations rather than proof of every recorded decision.

## Examples that matter

| ID / video time | Physical interpretation | Visible detector behavior | Why review it |
| --- | --- | --- | --- |
| A01 / 15.25–16.25 s | Small shift left | No event seen | A visible shift need not be fast enough or tilted enough for either horizontal rule. Confirm whether a command was intended. |
| A05 / 26.5–28.25 s | Lean left | STEP_L → LEFT | A useful positive shape example. Sampled lean reaches about −0.22. |
| A06 / 28.25–29.75 s | Lean right | No new event seen | Sampled lean reaches about +0.18, below the +0.20 entry threshold. Confirm desired sensitivity. |
| A07 / 41.75–43.25 s | One apparent jump cycle | STEP_R, HOP, STEP_LEFT, HOP, STEP_LEFT | Two jump entries and several lateral entries. The recognizers can respond independently to one action. |
| A08 / 55.75–57.5 s | Squat, then stand | DUCK, then HOP | A probable recovery false trigger unless a hop was intentional. |
| A18 / 86.25–87.25 s | Jump | HOP | A useful positive motion example with one jump entry. |
| A24 / 113–115.5 s | Move right and settle | STEP_RIGHT, STEP_L, STEP_R | Whole-body travel and torso tilt disagree, then each produces an event. |
| A30 / 137.5–139 s | Squat, then rise with left tilt | DUCK, then STEP_L | Recovery can trigger a different recognizer even when it does not trigger a jump. |
| A32 / 139.75–140.75 s | Continue moving left with counter-tilt | STEP_R, STEP_LEFT | Opposing directions can be valid measurements of different parts of one movement. Intent must decide which matters. |

No accuracy percentage is reported because the intended labels remain unconfirmed.

## What the checked-out code actually measures

The active detector is `laptop (royal)/pose_controller.py`. It currently uses these rules:

| Recognizer | Measurement | When it fires / releases |
| --- | --- | --- |
| Left/right lean | Shoulder-midpoint x minus hip-midpoint x, divided by current projected shoulder width, minus the same ratio at calibration | Enters at ±0.20; releases near ±0.12. Emits on entry. An upright body can move sideways without matching. |
| Left/right step | Hip x change over a recent roughly 0.20-second window, divided by elapsed time and current projected shoulder width | Enters at ±1.0 shoulder-widths/s. Recovery begins near 0.40; roughly 0.20 s of quiet motion re-arms. Recovery can suppress the immediate reverse movement. |
| Jump (HOP) | Upward hip speed between consecutive inference frames, divided by calibrated torso length; hip height compared with calibrated height | Speed must exceed 1.5 torso-lengths/s, rise must exceed 0.05 torso lengths, and 0.4 s must have passed since the previous hop. There is no complete takeoff/landing state machine. |
| Crouch (DUCK) | Fractional reduction in vertical hip-to-ankle span divided by current projected shoulder width, compared with calibration | Enters above 0.20 and releases near 0.12. Requires visible hips and ankles and a valid leg baseline. Crouch updates pause for 0.4 s after a hop. |

The camera image is mirrored before inference. Direction signs follow the mirrored image. The panel's `lean_old`, `duck_old`, `step_old`, and `hip_x` are comparison measurements; they do not directly trigger those gesture rules. A person moving down on screen therefore does not automatically mean DOWN.

The code can append a lean, jump, crouch, and step in the same frame. There is no rule that explains them as competing parts of one intended action. The adapter deduplicates equal swipe directions within one frame, but events on different frames can still become separate swipes.

Several limits follow directly from these calculations:

- A slow side shift can miss the speed threshold while its upright torso misses the tilt threshold.
- A fast upward tracking change or standing recovery can satisfy the jump rule if the calibrated height test also passes.
- Projected shoulder width changes with turning as well as distance. Dividing by a smaller width can inflate a measurement. This is a code-derived risk, not a measured diagnosis of every clip.
- Jump height and speed use the original calibrated torso length and image height. Moving closer or farther can change those measurements without an equivalent physical action.
- The jump cooldown permits another hop after 0.4 s even if the previous physical jump has not fully completed.

## Start and end frames: useful, but retain the path

We can calculate displacement and direction from landmark coordinates. For a chosen body center, displacement is `end − start`; speed also uses elapsed time. Averaging several relevant landmarks can reduce dependence on a single noisy point.

But displacement cannot identify every action. A jump returns to its starting height. A squat-and-rise also returns to its starting height. Their endpoints can be almost identical, despite different intermediate paths. A sidestep's return can look like a new opposite command. Position changes can also come from depth changes, turning, camera motion, or tracker error.

Keep a short timestamped history and interpret its phases: neutral, action begins, action continues, recovery, re-armed. For a jump, useful evidence includes upward travel followed by descent. For a crouch, useful evidence includes sustained body compression or bent knees followed by extension. We should emit early when evidence is sufficient, then use later frames to manage recovery; waiting for the end of the full sequence would add control latency.

## Your reference-pose idea

Yes: store reference landmark arrangements and calculate similarity. This can be deterministic template matching, without training a gesture neural network. It would let you see and edit what a gesture means.

For pose shape, first account for image aspect ratio, subtract a body anchor, and divide by a stable body scale. Compare relevant joints or joint angles with the reference. An illustrative score is a weighted average squared distance between corresponding normalized landmarks. Each definition should specify which joints matter, acceptable variation, minimum visibility, and required duration. Several captured examples can represent natural variation better than one ideal drawing.

Two cautions are fundamental:

1. Always allow neutral, unknown, and insufficient tracking. The closest template can still be a terrible match. Require an acceptable distance and enough separation from competing templates, with enough visible required joints.
2. Keep whole-body motion separately. Subtracting the hip center from every point removes translation: an upright sidestep then looks identical to standing still. Rotating a skeleton to make the torso upright can similarly erase the lean we want to detect.

I would prefer "capture my pose" as the initial authoring method, then let you drag points to adjust it. Dragging alone can create a pattern that your body or the landmark detector will never produce. A useful editor would show your recorded example, the reference, tolerance regions, the current score, and the specific joints that caused rejection.

For actions, store short example trajectories as well as poses. A fixed-duration comparison is a simple starting point. If speed differences cause failures, constrained dynamic time warping is a deterministic way to align sequences performed at different rates. It still needs rejection thresholds, action segmentation, and recovery handling. See the researchers' [UCR time-series matching work](https://www.cs.ucr.edu/~eamonn/UCRsuite.html). This is a candidate approach, not an evaluated implementation for Body Controller.

MediaPipe already uses ML to estimate body landmarks. It returns both image and estimated world coordinates, as described in the [official Pose Landmarker guide](https://developers.google.com/edge/mediapipe/solutions/vision/pose_landmarker?hl=en). Those estimates can support shape features, but do not by themselves prove global body travel or eliminate camera and tracking errors.

## Proposed next experiment

1. Correct the yellow columns, especially whether a return should produce an opposite action and whether the mixed jump/step examples were intentional combinations.
2. Capture timestamped landmarks, visibility, calibration, measurements, candidate scores, state transitions, emitted events, and output acknowledgments in a replayable recording. This avoids having to reconstruct numerical decisions from a screen recording.
3. Build one offline recognizer experiment for horizontal movement. Compare current thresholds against a shape-plus-trajectory template approach on corrected examples and neutral/repositioning examples. Keep examples from a later recording separate for evaluation.
4. Make the debug view explain each decision: matching example, relevant points, threshold/score, competing candidates, and recovery reason. Show recognition separately from mapped output and delivery.
5. Add jump/crouch phase handling, then test speed, camera distance, diagonal motion, partial visibility, repeated actions, and return trips.

Gesture definitions should describe physical recognition and emit canonical events. Profiles should continue mapping those events to game controls. Before giving sidesteps their own canonical event, resolve the existing naming mismatch (`STEP_L` means lean, while `STEP_LEFT` means travel) and decide whether the shared vocabulary needs an extension. Game controls must not become recognizer labels.

A learned classifier becomes worth comparing if corrected data shows that transparent features and templates still confuse actions across new sessions or people. It would require diverse labeled examples and held-out evaluation; this one recording is a debugging set, not evidence of generalization. The next useful step is to define the behavior you want and make its decisions replayable.

This review changes no runtime code and makes no changes to `/mobile`.
