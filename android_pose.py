"""Run Royal's detector with Android swipe output (BlueStacks, emulator, or phone)."""

import argparse
import importlib.util
import queue
import threading
from pathlib import Path

from android_swipe import AndroidSwipeClient
from mobile.ipad_output import frame_directions


class AndroidOutput:
    """One worker owns the Android connection so swipes never block pose inference."""

    def __init__(self, serial: str, dry_run=False):
        self.serial = serial
        self.dry_run = dry_run
        self.queue = queue.Queue()
        self.error = None
        self.sent = 0
        self.client = None
        self.thread = threading.Thread(target=self._worker, daemon=True)

    def start(self):
        if not self.dry_run:
            self.client = AndroidSwipeClient(self.serial)
            self.client.start()
            width, height = self.client.size
            print(f"Android connected: {self.serial}, screen {width}x{height}")
        self.thread.start()

    def submit_frame(self, frame: dict):
        """Nonblocking callback for the detector's gesture_frame output."""
        if self.error is None:
            for direction in frame_directions(frame):
                self.queue.put(direction)

    def _worker(self):
        while True:
            direction = self.queue.get()
            if direction is None:
                return
            try:
                elapsed = 0 if self.dry_run else self.client.native_swipe(direction)
            except OSError as exc:
                self.error = str(exc)
                print(f"Android output stopped: {exc}. No swipe was retried.", flush=True)
                return
            self.sent += 1
            label = "dry run" if self.dry_run else "sent"
            print(f"Android {direction}: {label} ({elapsed:.0f} ms)", flush=True)

    def close(self):
        self.queue.put(None)
        if self.thread.is_alive():
            self.thread.join(timeout=2)
        if self.client is not None:
            self.client.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--serial", default="127.0.0.1:5555",
                        help="adb device serial; BlueStacks defaults to 127.0.0.1:5555")
    parser.add_argument("--dry-run", action="store_true",
                        help="Track movement without sending touches")
    args = parser.parse_args()
    path = Path(__file__).resolve().parent / "laptop (royal)" / "pose_controller.py"
    spec = importlib.util.spec_from_file_location("royal_pose_controller", path)
    detector = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(detector)
    output = AndroidOutput(args.serial, dry_run=args.dry_run)
    try:
        output.start()
        print("Android output ready. Press C in the camera window to calibrate; Q quits.")
        detector.main(on_gesture_frame=output.submit_frame)
    except KeyboardInterrupt:
        pass
    finally:
        output.close()
        detector.cv2.destroyAllWindows()
        print(f"Android output: {output.sent} swipes sent.")
        if output.error:
            print(f"Last Android error: {output.error}")


if __name__ == "__main__":
    main()
