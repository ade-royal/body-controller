"""Run Royal's detector with the separate native iPad swipe output."""

import argparse
import importlib.util
from pathlib import Path

from devicekit_swipe import DeviceKitSwipeClient, FastDeviceKitSwipeClient
from ios_swipe import WdaSwipeClient
from mobile.ipad_output import IpadOutput


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--backend", choices=("fast", "devicekit", "wda"), default="fast"
    )
    parser.add_argument("--url", help="Override the selected helper's localhost URL")
    parser.add_argument(
        "--dry-run", action="store_true", help="Track movement without sending touches"
    )
    args = parser.parse_args()
    path = Path(__file__).resolve().parent / "laptop (royal)" / "pose_controller.py"
    spec = importlib.util.spec_from_file_location("royal_pose_controller", path)
    detector = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(detector)
    client_factory = {
        "devicekit": DeviceKitSwipeClient,
        "fast": FastDeviceKitSwipeClient,
        "wda": WdaSwipeClient,
    }[args.backend]
    url = args.url or (
        "http://127.0.0.1:12004" if args.backend != "wda" else "http://127.0.0.1:8100"
    )
    output = IpadOutput(url, dry_run=args.dry_run, client_factory=client_factory)
    try:
        output.start()
        print("iPad output ready. Press C in the camera window to calibrate; Q quits.")
        detector.main(on_gesture_frame=output.submit_frame)
    except KeyboardInterrupt:
        pass
    finally:
        output.close()
        detector.cv2.destroyAllWindows()
        print(
            f"iPad output: {output.sent} sent, {output.skipped} skipped while unavailable/busy."
        )
        if output.error:
            print(f"Last iPad error: {output.error}")


if __name__ == "__main__":
    main()
