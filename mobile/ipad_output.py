"""Translate gesture events to iPad swipes without blocking pose inference."""

import threading

from devicekit_swipe import FastDeviceKitSwipeClient

GESTURE_TO_SWIPE = {
    "LEFT": "LEFT",
    "RIGHT": "RIGHT",
    "UP": "UP",
    "DOWN": "DOWN",
    "STEP_L": "LEFT",
    "STEP_R": "RIGHT",
    "STEP_LEFT": "LEFT",
    "STEP_RIGHT": "RIGHT",
    "HOP": "UP",
    "DUCK": "DOWN",
    "LEAN_LEFT": "LEFT",
    "LEAN_RIGHT": "RIGHT",
    "JUMP": "UP",
    "CROUCH": "DOWN",
}


def frame_directions(frame: dict) -> list[str]:
    """Map new events only; held poses never repeat a swipe."""
    directions = []
    for event in frame.get("events", []):
        direction = GESTURE_TO_SWIPE.get(event.upper())
        if direction and direction not in directions:
            directions.append(direction)
    return directions


class IpadOutput:
    """One worker owns iPad input. Busy events are discarded rather than delayed."""

    def __init__(
        self,
        url="http://127.0.0.1:12004",
        dry_run=False,
        client_factory=FastDeviceKitSwipeClient,
    ):
        self.url = url
        self.dry_run = dry_run
        self.client_factory = client_factory
        self.condition = threading.Condition()
        self.connected = threading.Event()
        self.pending = None
        self.busy = False
        self.stopping = False
        self.error = None
        self.sent = 0
        self.skipped = 0
        self.thread = threading.Thread(target=self._worker, daemon=True)

    def start(self):
        self.thread.start()
        if not self.connected.wait(10):
            self.close()
            raise RuntimeError("Timed out connecting to the iPad helper")
        if self.error:
            self.close()
            raise RuntimeError(self.error)

    def submit_frame(self, frame: dict):
        """Nonblocking callback for the detector's gesture_frame output."""
        for direction in frame_directions(frame):
            self.submit(direction)

    def submit(self, direction: str) -> bool:
        """Accept one fresh direction only when the worker is idle."""
        direction = GESTURE_TO_SWIPE.get(direction.upper())
        if direction is None:
            raise ValueError("Unknown gesture or swipe direction")
        with self.condition:
            if self.stopping or self.error or not self.connected.is_set() or self.busy:
                self.skipped += 1
                return False
            self.pending = direction
            self.busy = True
            self.condition.notify()
            return True

    def _worker(self):
        client = None
        try:
            if not self.dry_run:
                client = self.client_factory(self.url)
                client.start()
            self.connected.set()
            while True:
                with self.condition:
                    self.condition.wait_for(
                        lambda: self.stopping or self.pending is not None
                    )
                    if self.stopping:
                        break
                    direction, self.pending = self.pending, None
                elapsed = 0 if self.dry_run else client.native_swipe(direction)
                with self.condition:
                    self.sent += 1
                    self.busy = False
                    self.condition.notify_all()
                label = "dry run" if self.dry_run else "acknowledged"
                print(f"iPad {direction}: {label} ({elapsed:.0f} ms)", flush=True)
        except Exception as exc:  # noqa: BLE001 - Any worker failure must stop device output.
            with self.condition:
                self.error = str(exc)
                self.busy = False
                self.pending = None
                self.condition.notify_all()
            print(f"iPad output stopped: {exc}. No swipe was retried.", flush=True)
        finally:
            self.connected.set()
            if client is not None:
                client.close()

    def close(self):
        with self.condition:
            self.stopping = True
            self.pending = None
            self.condition.notify_all()
        if self.thread.is_alive():
            self.thread.join(timeout=3.5)
