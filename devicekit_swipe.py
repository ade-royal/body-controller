"""Send directional iPad gestures through a running DeviceKit test helper."""

import http.client
import json
import math
import time
from urllib.parse import urlsplit

from ios_swipe import ALIASES, DIRECTIONS


class DeviceKitSwipeClient:
    """One persistent connection; a failed gesture is never replayed."""

    def __init__(self, url="http://127.0.0.1:12004", timeout=3.0):
        parsed = urlsplit(url)
        if (
            parsed.scheme != "http"
            or not parsed.hostname
            or parsed.path not in ("", "/")
        ):
            raise ValueError("Provide an HTTP DeviceKit URL without a path")
        self.connection = http.client.HTTPConnection(
            parsed.hostname, parsed.port or 80, timeout=timeout
        )
        self.request_id = 0
        self.size = None

    def request(self, method, params=None):
        self.request_id += 1
        payload = json.dumps(
            {
                "jsonrpc": "2.0",
                "id": self.request_id,
                "method": method,
                "params": params or {},
            }
        )
        try:
            self.connection.request(
                "POST",
                "/rpc",
                payload,
                {"Content-Type": "application/json", "Connection": "keep-alive"},
            )
            response = self.connection.getresponse()
            data = json.loads(response.read())
        except (OSError, http.client.HTTPException, ValueError):
            self.connection.close()
            raise
        if response.status >= 400 or "error" in data:
            raise RuntimeError(data.get("error", "DeviceKit request failed"))
        if data.get("id") != self.request_id or "result" not in data:
            raise RuntimeError("Unexpected DeviceKit response")
        return data["result"]

    def start(self):
        info = self.request("device.info")
        size = info["screenSize"]
        width, height = size["width"], size["height"]
        if not all(math.isfinite(value) and value > 0 for value in (width, height)):
            raise RuntimeError("DeviceKit reported an invalid screen size")
        self.size = (width, height)

    def native_swipe(self, direction):
        """Use DeviceKit's short gesture path with a guaranteed touch release."""
        direction = ALIASES.get(direction.upper(), direction.upper())
        if direction not in DIRECTIONS:
            raise ValueError(
                "Expected LEFT, RIGHT, UP, DOWN, STEP_L, STEP_R, HOP, or DUCK"
            )
        if self.size is None:
            raise RuntimeError("Start DeviceKit before sending gestures")
        width, height = self.size
        dx, dy = DIRECTIONS[direction]
        x, y = round(width * 0.5), round(height * 0.5)
        end_x = round(x + width * 0.2 * dx)
        end_y = round(y + height * 0.2 * dy)
        started = time.perf_counter()
        result = self.request(
            "device.io.gesture",
            {
                "actions": [
                    {"type": "press", "duration": 0, "x": x, "y": y, "button": 0},
                    {
                        "type": "move",
                        "duration": 0.02,
                        "x": end_x,
                        "y": end_y,
                        "button": 0,
                    },
                    {
                        "type": "release",
                        "duration": 0,
                        "x": end_x,
                        "y": end_y,
                        "button": 0,
                    },
                ]
            },
        )
        if result.get("success") is not True:
            raise RuntimeError("DeviceKit did not confirm the gesture")
        return (time.perf_counter() - started) * 1000

    def close(self):
        self.connection.close()


class FastDeviceKitSwipeClient(DeviceKitSwipeClient):
    """Use the patched helper's prepared geometry and cached daemon connection."""

    def start(self):
        super().start()
        result = self.request("device.io.fastSwipe.prepare")
        if result.get("success") is not True:
            raise RuntimeError("Fast swipe preparation failed")

    def native_swipe(self, direction, offset=None):
        """Send one fast swipe. ``offset`` is the touch timeline in seconds.

        The return value remains the full request-to-acknowledgment time.
        ``last_synthesize_ms`` is the helper's on-device ``proxy.synthesize``
        duration when the instrumented runner reports it.
        """
        direction = ALIASES.get(direction.upper(), direction.upper())
        if direction not in DIRECTIONS:
            raise ValueError(
                "Expected LEFT, RIGHT, UP, DOWN, STEP_L, STEP_R, HOP, or DUCK"
            )
        if self.size is None:
            raise RuntimeError("Start DeviceKit before sending gestures")
        params = {"direction": direction.lower()}
        if offset is not None:
            if not 0.01 <= offset <= 0.07:
                raise ValueError("offset must be from 0.01 through 0.07 seconds")
            params["offset"] = offset
        started = time.perf_counter()
        result = self.request("device.io.fastSwipe", params)
        if result.get("success") is not True:
            raise RuntimeError("Fast swipe was not confirmed")
        synthesize = result.get("synthesizeMs")
        if offset is not None and not isinstance(synthesize, (int, float)):
            raise RuntimeError(
                "Helper did not report synthesize time. Install the instrumented "
                "fast runner before comparing swipe offsets; this request's offset "
                "was not applied."
            )
        self.last_synthesize_ms = None if synthesize is None else float(synthesize)
        return (time.perf_counter() - started) * 1000
