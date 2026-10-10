"""Check touch direction, orientation, and failure handling against a local WDA stand-in."""

import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

from ios_swipe import WdaSwipeClient


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def handle_request(self):
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length)) if length else None
        self.server.calls.append((self.command, self.path, body))
        if self.path == "/status":
            status, value = 200, {"ready": True}
        elif self.path == "/session":
            status, value = 200, {"sessionId": "test-session"}
        elif self.path.endswith("/window/size"):
            status, value = 200, self.server.sizes.pop(0)
        elif self.path.endswith("/appium/settings"):
            status, value = 200, body["settings"]
        elif self.server.fail_actions:
            status, value = 500, {"error": "unknown error", "message": "Touch rejected"}
        else:
            status, value = 200, None
        data = json.dumps({"value": value}).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    do_GET = handle_request
    do_POST = handle_request


class SwipeBridgeTests(unittest.TestCase):
    def setUp(self):
        self.server = HTTPServer(("127.0.0.1", 0), Handler)
        self.server.calls = []
        self.server.sizes = [{"width": 834, "height": 1194}]
        self.server.fail_actions = False
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.client = WdaSwipeClient(f"http://127.0.0.1:{self.server.server_port}")

    def tearDown(self):
        self.client.close()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def test_connection_check_sends_no_touch_or_session(self):
        self.assertTrue(self.client.check()["ready"])
        self.assertEqual(self.server.calls, [("GET", "/status", None)])

    def test_all_four_directions_send_touch_and_release(self):
        self.client.start()
        self.server.sizes *= 4
        for direction, axis, sign in (
            ("LEFT", "x", -1),
            ("RIGHT", "x", 1),
            ("UP", "y", -1),
            ("DOWN", "y", 1),
        ):
            self.client.swipe(direction)
            method, path, body = self.server.calls[-1]
            self.assertEqual((method, path), ("POST", "/session/test-session/actions"))
            actions = body["actions"][0]["actions"]
            self.assertEqual(actions[1]["type"], "pointerDown")
            self.assertEqual(actions[-1]["type"], "pointerUp")
            self.assertGreater(sign * (actions[2][axis] - actions[0][axis]), 0)
            other = "y" if axis == "x" else "x"
            self.assertEqual(actions[2][other], actions[0][other])

    def test_rotation_uses_current_screen_dimensions(self):
        self.client.start()
        self.server.sizes = [
            {"width": 1194, "height": 834},
            {"width": 834, "height": 1194},
        ]
        self.client.swipe("LEFT")
        first = self.server.calls[-1][2]["actions"][0]["actions"][0]
        self.client.swipe("LEFT")
        second = self.server.calls[-1][2]["actions"][0]["actions"][0]
        self.assertEqual((first["x"], first["y"]), (597, 417))
        self.assertEqual((second["x"], second["y"]), (417, 597))

    def test_animation_wait_disabled_and_cached_size_avoids_per_swipe_query(self):
        self.client.cache_screen_size = True
        self.client.start()
        self.client.swipe("LEFT")
        self.client.swipe("RIGHT")
        settings = [
            body
            for _, path, body in self.server.calls
            if path.endswith("/appium/settings")
        ]
        self.assertEqual(
            settings,
            [{"settings": {"animationCoolOffTimeout": 0, "waitForIdleTimeout": 0}}],
        )
        self.assertEqual(
            sum(path.endswith("/window/size") for _, path, _ in self.server.calls), 1
        )
        self.server.sizes = [{"width": 1194, "height": 834}]
        self.client.refresh_screen_size()
        self.client.swipe("UP")
        start = self.server.calls[-1][2]["actions"][0]["actions"][0]
        self.assertEqual((start["x"], start["y"]), (597, 417))

    def test_rejected_gesture_is_not_retried(self):
        self.client.start()
        self.server.fail_actions = True
        with self.assertRaisesRegex(RuntimeError, "Touch rejected"):
            self.client.swipe("UP")
        self.assertEqual(
            sum(path.endswith("/actions") for _, path, _ in self.server.calls), 1
        )

    def test_invalid_event_makes_no_network_request(self):
        with self.assertRaises(ValueError):
            self.client.swipe("NONE")
        self.assertEqual(self.server.calls, [])

    def test_existing_motion_event_names_are_accepted(self):
        self.client.start()
        self.client.swipe("HOP")
        actions = self.server.calls[-1][2]["actions"][0]["actions"]
        self.assertLess(actions[2]["y"], actions[0]["y"])

    def test_native_swipe_uses_one_request_without_screen_query(self):
        self.client.start()
        self.server.calls.clear()
        for direction in ("LEFT", "RIGHT", "HOP", "DUCK"):
            self.client.native_swipe(direction)
        self.assertEqual(
            [body["direction"] for _, _, body in self.server.calls],
            ["left", "right", "up", "down"],
        )
        self.assertTrue(
            all(path.endswith("/wda/swipe") for _, path, _ in self.server.calls)
        )
        self.assertEqual(len(self.server.calls), 4)

    def test_native_failure_is_not_replayed(self):
        self.client.start()
        self.server.calls.clear()
        self.server.fail_actions = True
        with self.assertRaisesRegex(RuntimeError, "Touch rejected"):
            self.client.native_swipe("LEFT")
        self.assertEqual(len(self.server.calls), 1)


if __name__ == "__main__":
    unittest.main()
