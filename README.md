# body-controller
Keyboard, mouse, touch, ... excercise?? 

A new experimental general input interface for computers and mobile devices.

The current pose detector is `laptop (royal)/pose_controller.py` from `main`.

## Android (default)

Body movements become real touch swipes on any Android device reachable by adb:
BlueStacks, the Android emulator, or a USB phone. Start BlueStacks with
**Settings → Advanced → Android Debug Bridge** turned on, open the game, then run
from the repository root:

```powershell
.\.venv\Scripts\python.exe android_pose.py
```

Press **C** in the camera window and hold a neutral stance for three seconds.
Step left/right, jump, or crouch to swipe. Lean inputs are disabled. **Q** quits. Use `--dry-run`
to see outputs without touching the device, and `--serial` for a device other
than BlueStacks' default `127.0.0.1:5555`. To test swipes without the camera:
`.\.venv\Scripts\python.exe android_swipe.py LEFT RIGHT UP DOWN`.

Swipes go through a pinned scrcpy-server (downloaded once and checksum-verified
into `.android-tools/`) over one persistent adb connection. Sending a swipe takes
about 34 ms, most of it the deliberate finger-slide, versus about 300 ms
acknowledgment for the iPad path below. adb comes from Android platform-tools
(`ANDROID_HOME`, the default SDK folder, or `PATH`).

## iPad

To send detected movements to the connected iPad instead, run from the repository root:

```powershell
.\.venv\Scripts\python.exe ipad_pose.py
```

Keep the DeviceKit helper and USB port forward running, open the game, then press
**C** in the camera window and hold a neutral stance for three seconds.
Step left/right, jump, or crouch to send the matching swipe. Lean inputs are disabled. **Q** quits.
Try `--dry-run` first to see the movement outputs without sending touches.
Install camera dependencies using `laptop (royal)/requirements.txt`.

The iPad adapter runs separately from the camera loop and skips new inputs while
a swipe is busy. The custom DeviceKit fast swipe is the default; use
`--backend devicekit` for the original gesture method or `--backend wda` for
WebDriverAgent. Ten alternating swipes per DeviceKit method measured median
acknowledgment of 303 ms for the custom path versus 344 ms for the original.
These are not movement-to-screen timings, and the delay is still significant.
See [IOS_SETUP.md](IOS_SETUP.md) for iPad or iPhone helper setup and launch instructions.

## Movement recognition

Calibrate while standing still, facing the camera. Keep your full body and feet
visible for the strongest jump/crouch evidence. Recalibrate after a substantial
change in camera placement or your distance from it.

Directions require sustained travel of both hips and shoulders. A deliberate
return trip counts as another direction; holding a position does not repeat it.
Jump detection checks coordinated upward movement and visible foot rise, then
waits for landing before another jump. Rising from a crouch alone is insufficient.
When feet are cropped, jumps require a larger body rise and crouch recognition is
unavailable. Directions remain available during a jump.

The camera panel shows travel, speed, takeoff evidence and action phases. See
[the recognition review](docs/gesture-recognition-results.md) for replay results,
the remaining direction disagreement and a short live-test sequence.
