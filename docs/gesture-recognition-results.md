# First recognition improvement: results

The current detector now disables lean inputs, measures deliberate lateral travel, accepts return trips and tracks jumps through landing. Jump candidates need coordinated hip/shoulder rise and, when observable, foot rise. Crouch recovery alone cannot establish takeoff. Directions remain available while jumping.

No new runtime dependencies or trained model were added. The existing event names and output-adapter contract are preserved. The camera panel exposes measurements, action phases and rejection reasons. Tracking gaps clear motion history and release held output; a stable standing observation is required before recognizing another jump or crouch.

## Replay against the edited labels

Fresh MediaPipe inference ran over 4,229 frames from the camera region of `failurvid.mp4`, at 30 fps. The existing drawn skeleton is present in that recording and may affect inference. The same cached landmarks and a standing baseline from 9–10 seconds were fed to the saved pre-change detector and the revised detector. Video timestamps drive motion logic; computation speed does not.

This replay differs from the original live run: sampling, compression, pose inference and calibration can change events. The old replay is a comparison on identical input, not a reproduction of every event visible in the original log. No game inputs were sent.

Expected sequences below were interpreted from the user-edited workbook and this chat. A16 uses the explicit jump note. Filled labels with Pending status are included; other unlabeled rows are excluded. Action boundaries are approximate, so events near boundaries require visual review. This footage was used for development and tuning, not an independent generalization test.

| Example | Expected | Old replay | Revised replay |
|---|---|---|---|
| A01 | none | none | none |
| A02 | none | none | none |
| A03 | STEP_LEFT | STEP_LEFT | STEP_LEFT |
| A04 | STEP_RIGHT | STEP_RIGHT | STEP_RIGHT |
| A05 | none | STEP_L | none |
| A06 | none | none | none |
| A07 | HOP | HOP | HOP |
| A08 | DUCK | DUCK | DUCK |
| A09 | STEP_LEFT | STEP_LEFT | STEP_LEFT |
| A10 | STEP_RIGHT | STEP_RIGHT | STEP_RIGHT |
| A11 | STEP_RIGHT | STEP_RIGHT, HOP | STEP_RIGHT |
| A12 | STEP_LEFT | STEP_LEFT, HOP | STEP_LEFT |
| A13 | STEP_RIGHT | STEP_RIGHT, HOP | STEP_RIGHT |
| A14 | STEP_LEFT | STEP_LEFT, HOP | STEP_LEFT |
| A16 | HOP | STEP_R, HOP, STEP_RIGHT, STEP_RIGHT | HOP |
| A23 | STEP_LEFT | STEP_LEFT, HOP | STEP_LEFT |
| A24 | STEP_RIGHT | STEP_RIGHT, HOP, STEP_L | STEP_RIGHT |
| A25 | STEP_RIGHT | STEP_LEFT, HOP | STEP_LEFT |

Exact event sequences match in 17 of these 18 selected windows for the revised detector, versus 9 for the old replay. This is a development comparison, not an accuracy claim across people or all movements.

All four labeled small-movement windows emit nothing. A07 and A16 emit one HOP each. A08 emits DUCK without HOP. Extra HOP events are removed in the labeled lateral windows A11, A12, A13, A14, A23 and A24. A10 still counts as a return movement.

Across the entire replay, old/new HOP totals are 15/4 and old/new lean totals are 10/0. Fewer events alone does not prove better recognition; the selected-label comparison above checks whether intended actions were retained. Direction and crouch events outside those selected windows need further labeling before scoring.

## Remaining limitations

- **A25 remains a disagreement:** the user expects RIGHT, while both old and revised replay emit STEP_LEFT. The cached hip and shoulder centers both decrease in camera x through that interval. That evidence does not establish the user's intended action or settle direction conventions. Review the segment live before changing the direction rule; do not add a clip-specific exception.
- No new person or live game has been tested in this iteration. Simulated body sizes/frame rates test calculations, not real-world generalization.
- Feet must be visible for crouch detection and the strongest jump evidence. Cropped or occluded feet use a stricter jump fallback; small jumps can be missed.
- Calibration still uses C and a three-second standing observation. Small body-scale changes adapt slowly during stable standing; recalibrate after substantial distance/camera changes.
- Deliberate directions need meaningful travel and speed. This reduces small-motion triggers at the cost of some delay or missed subtle movements. In A03/A04/A09/A10, revised replay triggers about 0.10–0.17 seconds later than the old replay. These are replay differences, not measured camera-to-game latency.
- The separate iPad output adapter still discards inputs while busy. Recognition can emit jump then right, but iPad delivery can drop the second input. Android uses its existing queued output. Neither output policy was changed.

## Validation

85 automated tests pass across recognition, the actual camera-loop wiring with simulated camera/pose data, Android dry-run mapping and existing iPad output tests. Ruff checks and formatting pass for changed Python files. Tests cover lean rejection, meaningful motion, immediate reversals, same-direction rearming, small jitter, spike rejection, jumping once per action, repeat jumps after landing, crouch recovery, cropped feet, tracking loss/reacquisition and jump followed by right while airborne. Camera/pose resources close even when the output callback fails.

## Live check

From the repository root, run:

```powershell
.\.venv\Scripts\python.exe android_pose.py --dry-run
```

Press C, stand still for three seconds with feet visible, then try:

1. Small fidgets and torso leans: expect no events.
2. Left, then immediate right: expect one direction each.
3. Left, pause, left again: expect two left events.
4. Jump and land: expect one HOP; repeat after landing.
5. Crouch and stand quickly: expect DUCK without HOP.
6. Jump, then deliberately travel right: expect HOP followed by STEP_RIGHT.
7. Leave/re-enter the frame: expect no event from the position change alone.

Then use the normal Android launch for a game check. Repeat the same sequence with a person whose footage was not used to tune the detector. Note missed actions, extras, duplicates, direction and perceived delay separately.

## Reproduce the recorded comparison

The baseline source, cropped video, landmark cache, copied user labels, event traces, signals and comparison JSON are under `outputs/recognition-review/`. The edited workbook was read only and is unchanged.

```powershell
ffmpeg -i failurvid.mp4 -vf "crop=1600:1200:1368:360,scale=640:480,fps=30" -an -c:v libx264 -preset ultrafast -crf 20 outputs/recognition-review/replay-camera.mp4
.\.venv\Scripts\python.exe "laptop (royal)/replay_video.py" outputs/recognition-review/replay-camera.mp4 outputs/recognition-review/landmarks.jsonl
.\.venv\Scripts\python.exe "laptop (royal)/compare_replay.py" outputs/recognition-review/landmarks.jsonl outputs/recognition-review/baseline_pose_controller.py outputs/recognition-review
```

The crop is specific to this desktop recording; other videos need their own camera region. Existing artifacts are available, so extracting/inferencing again is unnecessary unless the input or pose model changes. The comparison script updates event/signals traces; the table above records the reviewed implementation results.
