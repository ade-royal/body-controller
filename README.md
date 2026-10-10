# body-controller
Keyboard, mouse, touch, ... excercise?? 

A new experimental general input interface for computers and mobile devices.

The current pose detector is `laptop (royal)/pose_controller.py` from `main`.
To send its detected movements to the connected iPad, run from the repository root:

```powershell
.\.venv\Scripts\python.exe ipad_pose.py
```

Keep the DeviceKit helper and USB port forward running, open the game, then press
**C** in the camera window and hold a neutral stance for three seconds.
Lean or step left/right, jump, or crouch to send the matching swipe. **Q** quits.
Try `--dry-run` first to see the movement outputs without sending touches.
Install camera dependencies using `laptop (royal)/requirements.txt`.

The iPad adapter runs separately from the camera loop and skips new inputs while
a swipe is busy. The custom DeviceKit fast swipe is the default; use
`--backend devicekit` for the original gesture method or `--backend wda` for
WebDriverAgent. Ten alternating swipes per DeviceKit method measured median
acknowledgment of 303 ms for the custom path versus 344 ms for the original.
These are not movement-to-screen timings, and the delay is still significant.
See [IOS_SETUP.md](IOS_SETUP.md) for helper setup and launch instructions.
