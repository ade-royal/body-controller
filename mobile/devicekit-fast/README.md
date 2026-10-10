# Fast iPad swipe helper

`fast-swipe.patch` changes [DeviceKit iOS 0.0.33](https://github.com/mobile-next/devicekit-ios/releases/tag/0.0.33), pinned to commit `cbf1555d202e6b863bcf0cdc42954852bf6f5f12`. The patch adds two JSON-RPC methods:

- `device.io.fastSwipe.prepare` captures the foreground game's screen geometry and the XCTest daemon connection once. Call it after opening the game and again after changing games or rotating the iPad.
- `device.io.fastSwipe` takes `{ "direction": "left" }` (or right/up/down), sends a center-origin touch with 50 ms press and 20 ms movement, and releases it. It uses the prepared geometry without querying the foreground app for each swipe.

The original DeviceKit methods remain unchanged, allowing a direct latency comparison. The patch only changes two existing Swift files, so the original Xcode project compiles them without project-file edits. GitHub Actions builds an unsigned runner IPA; xtool signs it with the user's own developer account before installation. DeviceKit's [license](https://github.com/mobile-next/devicekit-ios/blob/0.0.33/LICENSE) still applies to the patched helper.

The [initial Mac build](https://github.com/ade-royal/body-controller/actions/runs/38044770550) succeeded. The workflow runs on `davidTests` and can also be started manually. Its artifact is `body-controller-fast-ipad-runner`. The contained `devicekit-ios-runner.ipa` is copied locally to `.ios-tools/body-controller-fast-runner.ipa`; install it with:

```powershell
powershell.exe -ExecutionPolicy Bypass -File .\setup_ipad.ps1 -Fast -Resume
```

The fast helper replaces the existing DeviceKit runner when signed under the same bundle ID. Launch it with the existing DeviceKit command and USB forward. `ipad_pose.py` and `ipad_arrows.py` now use `--backend fast` by default; `--backend devicekit` selects the original method. Keep the game in the foreground before starting the controller. Restart the controller after rotation or changing games so `prepare` captures the new geometry.

On the connected iPad Pro with Subway Surfers foregrounded, ten alternating requests per method produced a median acknowledgment of 303 ms for `fastSwipe` and 344 ms for the original `device.io.gesture`. These are request-completion times, not camera-to-game-response times.
