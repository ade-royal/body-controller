# Windows to iPad swipe prototype

The movement detector remains on Windows. `devicekit_swipe.py` now defaults to
the custom fast swipe method for LEFT, RIGHT, UP, and DOWN. `ios_swipe.py` is the
WebDriverAgent (WDA) fallback. Both accept STEP_L, STEP_R, HOP, and DUCK.
There is no change to the pose detector's classification.

## Use the faster helper on this machine

The [custom DeviceKit runner](mobile/devicekit-fast/README.md), built from
[DeviceKit v0.0.33](https://github.com/mobile-next/devicekit-ios/releases/tag/0.0.33),
is installed on this iPad. The [Mac build](https://github.com/ade-royal/body-controller/actions/runs/38044770550)
produced an unsigned IPA, which xtool signed with the existing developer account.
The local copy is `.ios-tools/body-controller-fast-runner.ipa`; to reinstall it:

```powershell
powershell.exe -ExecutionPolicy Bypass -File .\setup_ipad.ps1 -Fast -Resume
```

Trust or verify the signed developer profile in Settings → General → VPN &
Device Management when prompted. Replace the bundle ID placeholder with the
identifier shown by your signing tool. Start the installed runner and its USB
port forward in separate PowerShell terminals:

```powershell
.\.venv-ios\Scripts\python.exe .ios-tools\pmd_cli.py developer dvt xcuitest "YOUR_SIGNED_DEVICEKIT_RUNNER_BUNDLE_ID"
.\.venv-ios\Scripts\python.exe .ios-tools\pmd_cli.py usbmux forward 12004 12004
```

The bundle ID may change if re-signed. The original downloaded runner uses
`com.mobilenext.devicekit-iosUITests.xctrunner`. With Subway Surfers open, run
one of these controllers:

```powershell
.\.venv\Scripts\python.exe ipad_pose.py
.\.venv-ios\Scripts\python.exe ipad_arrows.py
```

Both default to the custom fast method. `--backend devicekit` uses the original
DeviceKit gesture method in the same helper, and `--backend wda` uses the earlier
WDA helper on port 8100. Run only one controller at a time. The fast method
prepares the foreground game's geometry once when the controller starts, then
reuses it for each swipe. Open the game before starting the controller. Restart
the controller after changing games or rotating the iPad.

In ten alternating left/right swipes per method using the same custom helper,
the fast command's median request acknowledgment was **303 ms**, versus **344 ms**
for the original DeviceKit gesture. This is a roughly 12% reduction. Earlier,
the original DeviceKit median was 346 ms versus 466 ms for WDA. We have not
measured the first visible game response, and 303 ms may still feel too slow
for gameplay. New gestures arriving
while one is in flight are still skipped rather than queued. These helpers are
testing tools, so this installation is a prototype path rather than a normal
consumer iPad app.

## Verified on this machine

- The connected iPad is an 11-inch iPad Pro (`iPad8,1`), iPadOS 17.6.1.
- USB trust and Developer Mode work.
- Apple's developer support image mounted successfully. Mount it again after
  a device reboot if required.
- xtool 1.21.0 runs under Ubuntu/WSL and sees the iPad through a private local
  bridge to the Windows Apple device service.
- Official WebDriverAgent v16.14.2 has been downloaded and packaged as an IPA.
  It declares minimum iOS 13.0 and has no embedded XCTest frameworks.
- xtool successfully signed and installed the helper. Its installed identifier is
  a signing-specific identifier based on `com.facebook.WebDriverAgentRunner.xctrunner`.
  After trusting the developer profile, the helper launched successfully and
  returned `ready: true` from `/status` through the localhost USB forward.
- The iPad's direct HID capability returned "not supported by this device".
  This prototype therefore uses WDA instead.
- Nine local integration tests cover directions, touch release, rotation, event
  aliases, and error handling. Four physical swipes were confirmed in-game;
  action acknowledgment took 1.4–2.2 seconds in the initial test.

## Sign and install the helper

Keep the iPad connected and unlocked. From PowerShell in this folder:

```powershell
powershell.exe -ExecutionPolicy Bypass -File .\setup_ipad.ps1
```

Enter Apple account credentials only into the local terminal prompts, never
into chat or command-line password arguments. The script uses xtool's
interactive sign-in and then attempts to sign/install the prepared IPA. Code
signing and launch compatibility must be verified on this device; successful
installation alone does not establish that WDA can run.

After signing in successfully, retry without another login using:

```powershell
powershell.exe -ExecutionPolicy Bypass -File .\setup_ipad.ps1 -Resume
```

`-Check` only checks USB discovery. The launcher uses WSL `--exec` to preserve
Windows path backslashes. Ubuntu's `zip` package is required for IPA packaging
and is now installed on this machine. The private USB bridge supplies the
validated local pairing record when xtool requests it; the older certificate
returned by the Windows Apple service caused `sslError` during device preparation.
Pairing keys are passed only through the private pipe and are not logged.

The downloaded tools, unsigned app, and local connection scripts are in the
ignored `.ios-tools/` folder. iPad tooling is isolated in `.venv-ios/`;
`requirements-ios.txt` records its main dependency. Recreating the prepared
xtool/helper cache is a separate setup step, not done by `setup_ipad.ps1`.

If requested on the iPad, trust the development profile under Settings →
General → VPN & Device Management. Keep Developer Mode enabled.

## Start the installed helper

Confirm the actual installed WDA bundle identifier before launching it; signing
may change it. The original unsigned identifier is
`com.facebook.WebDriverAgentRunner.xctrunner`.

One terminal runs the test helper (replace the bundle ID placeholder with the
identifier shown by your signing tool):

```powershell
.\.venv-ios\Scripts\python.exe .ios-tools\pmd_cli.py developer dvt xcuitest "YOUR_SIGNED_WDA_RUNNER_BUNDLE_ID"
```

A second terminal forwards only the local WDA port through USB:

```powershell
.\.venv-ios\Scripts\python.exe .ios-tools\pmd_cli.py usbmux forward 8100 8100
```

The project-local CLI wrapper prefers the validated local trust record over
the stale record returned by the Windows Apple service. It does not edit or
delete system pairing records. A successful WDA `/status` check is required
before sending gestures:

```powershell
.\.venv-ios\Scripts\python.exe ios_swipe.py --check
```

## Test actual swipes

The first four physical swipes were acknowledged by WDA and confirmed in-game
by the user. Action requests took 1.4–2.2 seconds; responsiveness needs tuning.

### Windows arrow keys

With the helper and USB forward running, launch:

```powershell
.\.venv-ios\Scripts\python.exe ipad_arrows.py
```

Open the game on the iPad and select the controller window on Windows. Arrow
keys send the corresponding swipe; Esc or closing the window stops input.
Each key must be released before another swipe. While a request is in flight,
new presses are skipped instead of queued. The status shows when it is ready
again. A swipe already sent may finish after the window closes. Connection
errors stop input; reopen the controller after restoring the helper.
Use `--dry-run` to try the keyboard window without touching the iPad.

The WDA backend disables WDA's animation cooldown (previously 2 seconds) and
uses `/wda/swipe` with velocity 5000 points/second. It sends one directional
request without querying screen dimensions. Native gestures determine their
own travel distance; the W3C path remains available in `ios_swipe.py` for explicit
coordinates/duration. Rotation no longer requires reopening the arrow controller.

Measured in Subway Surfers after disabling waits: cached W3C swipes took
779–786 ms; selecting the game explicitly gave 728–758 ms; shortening the W3C
gesture to 60 ms gave 449–695 ms; native left/right swipes gave 402–528 ms.
These are small samples of acknowledgment times, not camera-measured input-to-display
latency or a guarantee of gameplay responsiveness. The native benchmark used an
explicit active-game setting; the generic controller uses automatic foreground
selection. The remaining delay is still substantial for a reaction game.

Final latency pass (2026-10-10), four requests per method:

| Method | Median acknowledgment |
| --- | ---: |
| Native swipe, velocity 5000 (retained) | 404 ms |
| Native swipe, velocity 20000 | 401 ms |
| W3C 40 ms gesture, 15% screen distance | 559 ms |
| Coordinate drag, zero hold, velocity 5000 | 771 ms |
| Native swipe in a session attached to the running game | 383 ms |

The first four methods were interleaved; the attached-session check followed.
These small samples do not establish the 21 ms difference as a reliable win.
WDA's generic native method was retained as the fallback. No gesture failures
were retried.

The direct CoreDevice HID path was also checked with its required temporary
media session (no touches). The iPad rejected media startup with CoreDeviceError
9021: "Remote control requires iOS 27.0 or later on this device." No OS update
was attempted. This method is unavailable on the connected iPadOS 17.6.1 setup.

Royal's detector from `main` is now integrated through `ipad_pose.py` and
`mobile/ipad_output.py`. `pose_controller.main()` accepts an optional gesture-frame
callback; its standalone detector behavior remains available without the adapter.

```powershell
.\.venv\Scripts\python.exe ipad_pose.py --dry-run
.\.venv\Scripts\python.exe ipad_pose.py
```

Use the pose environment (`.venv`) for these commands, since it contains OpenCV,
MediaPipe, and NumPy. The swipe client itself uses the Python standard library;
the iPad tooling environment stays separate. Run only one arrow/pose output
controller at a time; DeviceKit uses a JSON-RPC server and WDA creates a session.

Open the intended game, press C in the camera window to calibrate, and hold
neutral for three seconds. Q exits. New `STEP_L`/`STEP_LEFT` events map to LEFT;
`STEP_R`/`STEP_RIGHT` map to RIGHT; `HOP` maps to UP; `DUCK` maps to DOWN.
Held lean/crouch states do not resend swipes. Multiple events with the same
direction in one frame are deduplicated. When simultaneous distinct events
occur, the first one is accepted if idle; the rest are skipped while busy.
The worker never blocks pose inference or queues old swipes. An output failure
stops further device input and is printed in the terminal; camera tracking can
continue until Q. Failed swipes are never replayed.

The previous local `pose_test.py` and its tests remain recoverable in the Git
stash named "Preserve iPad bridge and local detector before main integration".
They are not part of the active detector path.

Open the intended game on the iPad before running these commands. They target
the foreground app, with a swipe beginning at screen center:

```powershell
.\.venv-ios\Scripts\python.exe ios_swipe.py LEFT
.\.venv-ios\Scripts\python.exe ios_swipe.py RIGHT
.\.venv-ios\Scripts\python.exe ios_swipe.py UP
.\.venv-ios\Scripts\python.exe ios_swipe.py DOWN
```

`--duration-ms` defaults to 120 and `--distance` to 0.25 of the relevant screen
dimension. These are initial values to tune in the real game, not measured
latency guarantees. Screen dimensions are queried for each swipe to respect
orientation. No failed gesture is automatically retried, because a timed-out
request may already have executed.

For a persistent session accepting one event per input line:

```powershell
.\.venv-ios\Scripts\python.exe ios_swipe.py --stdin
```

Send one of the four directions or motion-event names per line; QUIT exits.
The command processes events sequentially, so an upstream movement producer
must avoid building a backlog. Movement-detector integration is deferred until
the four manual swipes and quick action sequences work on the device.

## Checks without touching the iPad

```powershell
.\.venv-ios\Scripts\python.exe ios_swipe.py LEFT --dry-run
.\.venv-ios\Scripts\python.exe -m unittest -v test_ios_swipe
```

## References

- [xtool](https://github.com/xtool-org/xtool)
- [DeviceKit iOS](https://github.com/mobile-next/devicekit-ios)
- [Direct HID/media-session implementation](https://github.com/doronz88/pymobiledevice3/blob/master/pymobiledevice3/remote/core_device/hid_service.py)
- [Upstream discussion of gesture overhead](https://github.com/appium/appium/issues/16230)
- [WDA native swipe implementation](https://github.com/appium/WebDriverAgent/blob/v16.14.2/WebDriverAgentLib/Commands/FBElementCommands.m)
- [WDA preinstalled helper setup](https://appium.github.io/appium-xcuitest-driver/latest/guides/run-preinstalled-wda/)
- [pymobiledevice3 iOS 17 tunnels](https://github.com/doronz88/pymobiledevice3/blob/master/docs/guides/ios17-tunnels.md)
