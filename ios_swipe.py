"""Send four directional touch gestures through an already-running WebDriverAgent.

This does not sign, install, or launch WebDriverAgent. Use --check to test its
connection, --dry-run to inspect gestures, and --stdin for movement events.
"""

import argparse
import http.client
import json
import math
import sys
import time
from urllib.parse import urlsplit

ALIASES = {"STEP_L": "LEFT", "STEP_R": "RIGHT", "HOP": "UP", "DUCK": "DOWN"}
DIRECTIONS = {"LEFT": (-1, 0), "RIGHT": (1, 0), "UP": (0, -1), "DOWN": (0, 1)}


def swipe_actions(direction, width, height, duration_ms=120, distance=0.25):
    """A center-origin touch, movement, and release in screen-point coordinates."""
    direction = ALIASES.get(direction.upper(), direction.upper())
    if direction not in DIRECTIONS:
        raise ValueError("Expected LEFT, RIGHT, UP, DOWN, STEP_L, STEP_R, HOP, or DUCK")
    if not all(math.isfinite(value) and value > 0 for value in (width, height)):
        raise ValueError("Screen dimensions must be finite and positive")
    if not 0 < distance < 0.45 or not 20 <= duration_ms <= 1000:
        raise ValueError(
            "Distance must be between 0 and 0.45; duration must be 20–1000 ms"
        )
    dx, dy = DIRECTIONS[direction]
    start = (round(width * 0.5), round(height * 0.5))
    end = (round(width * (0.5 + distance * dx)), round(height * (0.5 + distance * dy)))
    return {
        "actions": [
            {
                "type": "pointer",
                "id": "body-controller",
                "parameters": {"pointerType": "touch"},
                "actions": [
                    {
                        "type": "pointerMove",
                        "duration": 0,
                        "origin": "viewport",
                        "x": start[0],
                        "y": start[1],
                    },
                    {"type": "pointerDown", "button": 0},
                    {
                        "type": "pointerMove",
                        "duration": duration_ms,
                        "origin": "viewport",
                        "x": end[0],
                        "y": end[1],
                    },
                    {"type": "pointerUp", "button": 0},
                ],
            }
        ]
    }


class WdaSwipeClient:
    """Persistent connection; timed-out gestures are never automatically replayed."""

    def __init__(
        self, url="http://127.0.0.1:8100", timeout=3.0, cache_screen_size=False
    ):
        parsed = urlsplit(url)
        if (
            parsed.scheme != "http"
            or not parsed.hostname
            or parsed.path not in ("", "/")
        ):
            raise ValueError("Provide an HTTP WebDriverAgent URL without a path")
        self.connection = http.client.HTTPConnection(
            parsed.hostname, parsed.port or 80, timeout=timeout
        )
        self.session = None
        self.cache_screen_size = cache_screen_size
        self.screen_size = None

    def request(self, method, path, payload=None):
        body = None if payload is None else json.dumps(payload)
        try:
            self.connection.request(
                method, path, body, {"Content-Type": "application/json"}
            )
            response = self.connection.getresponse()
            data = json.loads(response.read())
        except (OSError, http.client.HTTPException, ValueError):
            self.connection.close()
            raise
        value = data.get("value")
        if response.status >= 400 or (isinstance(value, dict) and value.get("error")):
            message = (
                value.get("message", "WebDriverAgent request failed")
                if isinstance(value, dict)
                else str(value)
            )
            raise RuntimeError(message)
        return value

    def check(self):
        return self.request("GET", "/status")

    def start(self):
        value = self.request(
            "POST",
            "/session",
            {
                "capabilities": {
                    "alwaysMatch": {
                        "waitForIdleTimeout": 0,
                        "shouldWaitForQuiescence": False,
                        "shouldTerminateApp": False,
                    }
                }
            },
        )
        self.session = value["sessionId"]
        if not self.session:
            raise RuntimeError("WebDriverAgent did not create a session")
        self.request(
            "POST",
            f"/session/{self.session}/appium/settings",
            {"settings": {"animationCoolOffTimeout": 0, "waitForIdleTimeout": 0}},
        )
        self.screen_size = None
        if self.cache_screen_size:
            self.refresh_screen_size()

    def refresh_screen_size(self):
        self.screen_size = self.request("GET", f"/session/{self.session}/window/size")
        return self.screen_size

    def swipe(self, direction, duration_ms=120, distance=0.25):
        # CLI follows rotation; interactive controller opts into fixed orientation.
        swipe_actions(direction, 1, 1, duration_ms, distance)
        if self.session is None:
            raise RuntimeError("Start a WebDriverAgent session before sending gestures")
        started = time.perf_counter()
        size = self.screen_size if self.cache_screen_size else None
        if size is None:
            size = self.refresh_screen_size()
        payload = swipe_actions(
            direction, size["width"], size["height"], duration_ms, distance
        )
        self.request("POST", f"/session/{self.session}/actions", payload)
        return (time.perf_counter() - started) * 1000

    def close(self):
        self.connection.close()

    def native_swipe(self, direction, velocity=5000):
        """Use XCTest's directional swipe, avoiding W3C coordinate resolution."""
        direction = ALIASES.get(direction.upper(), direction.upper())
        if direction not in DIRECTIONS:
            raise ValueError("Expected a swipe direction or motion event name")
        if not math.isfinite(velocity) or velocity <= 0:
            raise ValueError("Velocity must be finite and positive")
        if self.session is None:
            raise RuntimeError("Start a WebDriverAgent session before sending gestures")
        started = time.perf_counter()
        self.request(
            "POST",
            f"/session/{self.session}/wda/swipe",
            {"direction": direction.lower(), "velocity": velocity},
        )
        return (time.perf_counter() - started) * 1000


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "direction", nargs="?", help="One direction or motion event name"
    )
    parser.add_argument("--url", default="http://127.0.0.1:8100")
    parser.add_argument("--duration-ms", type=int, default=120)
    parser.add_argument("--distance", type=float, default=0.25)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument(
        "--check", action="store_true", help="Check WDA without sending a gesture"
    )
    modes.add_argument(
        "--stdin", action="store_true", help="Read one direction per line; QUIT stops"
    )
    modes.add_argument(
        "--dry-run", action="store_true", help="Print gesture data without connecting"
    )
    parser.add_argument("--width", type=float, default=834, help="Dry-run width only")
    parser.add_argument(
        "--height", type=float, default=1194, help="Dry-run height only"
    )
    args = parser.parse_args()
    if args.dry_run:
        if not args.direction:
            parser.error("--dry-run requires a direction")
        print(
            json.dumps(
                swipe_actions(
                    args.direction,
                    args.width,
                    args.height,
                    args.duration_ms,
                    args.distance,
                ),
                indent=2,
            )
        )
        return
    if not args.direction and not args.check and not args.stdin:
        parser.error("Choose a direction, --check, or --stdin")
    client = WdaSwipeClient(args.url)
    try:
        if args.check:
            status = client.check()
            print(json.dumps({"ready": status.get("ready"), "os": status.get("os")}))
            return
        client.start()
        directions = sys.stdin if args.stdin else [args.direction]
        for line in directions:
            direction = line.strip().upper()
            if direction == "QUIT":
                break
            if not direction:
                continue
            elapsed = client.swipe(direction, args.duration_ms, args.distance)
            print(
                json.dumps({"direction": direction, "request_ms": round(elapsed, 1)}),
                flush=True,
            )
    finally:
        client.close()


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, RuntimeError, http.client.HTTPException) as exc:
        print(
            f"Swipe bridge stopped: {exc}. Check WDA and the USB connection; no gesture was retried.",
            file=sys.stderr,
        )
        sys.exit(1)
