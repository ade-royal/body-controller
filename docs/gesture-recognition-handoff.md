# Gesture recognition: plan and handoff

Updated: 2026-10-10. The user subsequently authorized implementation with "okay let's go build". The first geometry/state iteration is now implemented; see [results and live-test instructions](gesture-recognition-results.md). The discussion and original plan below are retained for context.

## Authorization and goal

The user originally asked to brainstorm and save this plan before changing models, then authorized building the first iteration. Alternative methods remain future comparisons, not a request to implement all of them now.

Improve reliability and fun for new players without requiring each player to record training examples. Aim for a focused first improvement in roughly 45 minutes once implementation is requested. This is a time budget for a limited iteration, not a promise of universal reliability. The user is interested in comparing multiple methods, starting with improving the current logic. Do not build all alternatives at once.

Preserve recognition -> gesture event -> configurable mapping -> output separation. Read AGENTS.md, README.md and docs/architecture.md before implementation. Do not modify /mobile or reorganize the repository as part of this work.

## Evidence and existing implementation

- Active detector: `laptop (royal)/pose_controller.py`; confirm current contents before editing. The repository's actual layout differs from the intended AGENTS.md layout.
- Default launcher: `android_pose.py`; inspect the actual adapter boundary before changing event identifiers. Existing names include HOP, DUCK, STEP_LEFT/STEP_RIGHT (travel) and STEP_L/STEP_R (lean).
- User recording: `failurvid.mp4`.
- User-edited labels: `outputs/failure-review/movement-review.xlsx`. Preserve this workbook; do not regenerate it. Read the user's ground truth, expected gestures and notes, including filled rows whose status remains Pending.
- Earlier analysis: `docs/movement-recognition-review.md`; original observations: `outputs/failure-review/observations.json`. These predate the user's corrections. The edited workbook and subsequent chat take precedence.
- Video review sampled frames and visible event logs. It did not establish exact trigger timestamps, prove game input delivery, or verify that the recorded code version matches the current checkout.

## Agreed behavior

- Disable lean recognition as a control trigger for now.
- Small incidental movements should emit nothing. A01, A02 and A06 are intended no-ops; A05's lean event is unwanted.
- Meaningful lateral movement is relative to the player's current position, not a fixed neutral location. Deliberate return trips and quick reversals must count (A10).
- One jump should emit one jump. Small sideways wobbles during takeoff must not cause direction events (A07, A16).
- Crouch followed by standing should not emit a jump (A08).
- Lateral travel should not emit spurious jumps (A12, A23).
- A25 was labeled RIGHT by the user, despite the earlier visual interpretation and detected LEFT. Investigate; its cause is unresolved.
- There is no need for a special sideways-jump gesture. For the user's Subway Surfers control example, jump then deliberate right movement should emit JUMP followed by RIGHT, including when the second action occurs while airborne. Do not block lateral recognition for the entire jump. Mapping to swipes remains outside recognition.

## Proposed first implementation

These are design proposals to validate, not established fixes or final threshold values.

1. Disable lean-generated events and held lean outputs. Preserve compatibility at the adapter boundary.
2. Stabilize measurements. Use a short timestamped movement history rather than consecutive-frame jump velocity. Use a reliable body-size estimate that does not fluctuate with instantaneous projected shoulder width. Update scale cautiously; reject low-confidence tracking and reset motion history across tracking gaps so reacquisition cannot create a false movement.
3. Repair lateral detection. Require meaningful body-relative displacement plus sustained directional evidence. Track each movement from its local start or turning point. Emit once per action. Permit a sufficiently clear opposite-direction action immediately without waiting for a return to neutral. Distinguish tiny reversals from deliberate ones and define when a new same-direction action begins.
4. Give jumps phases: ready, takeoff/active, landing/recovery. Emit once when takeoff evidence is sufficient, not after waiting for the full jump. Rearm based on action completion instead of a cooldown alone. Evaluate coordinated hip/shoulder rise and reliable leg/foot evidence; do not assume cropped feet provide trustworthy takeoff evidence.
5. Track crouch and recovery explicitly. Rising from a crouch alone is insufficient for a jump. Preserve the possibility of a real jump out of a crouch when additional takeoff evidence supports it. Assess knee bend/leg compression with confidence checks.
6. Keep direction recognition available during jumping, but require independent meaningful lateral travel. Avoid a blanket winner-takes-all rule that suppresses valid sequential actions.
7. Show why a candidate triggered or was rejected, using a small set of understandable signals and phase labels. Keep tunable values centralized. Avoid an elaborate editor in this iteration.

Current source facts motivating this proposal: lateral recovery explicitly swallows return trips; lateral speed divides by current shoulder width; jump uses previous-frame hip velocity, a neutral-height condition and a 0.4-second cooldown; recognizers can fire independently. These facts suggest failure mechanisms but do not prove the cause of every recorded error.

## Validation and the short time budget

- Preserve a baseline before changes. Check existing deterministic tests and add meaningful cases for reversals, small jitter, one event per jump, crouch recovery, tracking loss/reacquisition, and jump followed by intentional lateral travel.
- Evaluate labeled examples as event sequences, including expected no-ops. Report extra events, missed actions, wrong directions, duplicates and delay separately. Do not silently treat unlabeled examples as confirmed ground truth.
- Recorded event logs describe the old run. Evaluating the revised detector on video requires fresh landmark inference or saved landmark data, using video timestamps rather than playback execution speed. If no replay path exists, keep any new harness minimal and state how much of the budget it consumes.
- Reserve time for a live check. Fresh recordings from other people are necessary to assess generalization. If no other tester is available, report that limitation; passing this user's footage is not evidence of out-of-the-box performance for everyone.
- Prioritize disabling lean, correcting return-trip handling and reducing jump/recovery false positives. Do not promise every proposed improvement and cross-person validation fits within 45 minutes. Report remaining failures explicitly.

## Alternative methods for later comparison

Use the same labeled evaluation clips and unseen-person tests for each method.

1. Start/end motion matching: compare displacement and joint changes across short intervals. Simple directional alternative, but endpoints alone may confuse different actions.
2. Recorded movement templates: store sequences of body-relative measurements, not video appearance. Compare live sequences to multiple examples using time alignment, such as dynamic time warping. Preserve body travel separately from centered body shape; centering every frame on the hips would erase lateral movement. Reject poor or ambiguous matches instead of always choosing the closest. Complete-action matching introduces delay; early recognition needs separate validation and event lifecycle logic.
3. Reference poses: compare normalized body shapes or angles with predefined targets. Suitable for held poses; a static pose alone cannot establish travel direction or reliably distinguish jumping from standing up. A draggable pose editor was an idea, not an agreed build requirement.
4. Small learned classifier: possible later, using landmark features and motion history. Requires diverse positive examples and ordinary movement/recovery examples. No training is currently authorized.
5. Pretrained action-recognition model: possible research direction, with uncertain integration, label fit and control latency. Not the first short iteration.

Templates should be built from several people and tested on people excluded from template selection and threshold tuning. Normalization helps with body size and position but does not guarantee generalization. Handwritten thresholds can also overfit one person's footage. Optional personalization can come later; mandatory personal recording conflicts with the user's desired default experience.

Reference for sequence matching: https://www.eecs.ucf.edu/isuelab/research/jackknife
