"""Check DeviceKit's gesture contract without touching the iPad."""

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from devicekit_swipe import DeviceKitSwipeClient, FastDeviceKitSwipeClient


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_POST(self):
        length = int(self.headers["Content-Length"])
        body = json.loads(self.rfile.read(length))
        self.server.calls.append(body)
        if body["method"] == "device.info":
            result = {"screenSize": {"width": 834, "height": 1194}}
        elif self.server.reject:
            result = None
        else:
            result = {"success": True}
        response = {"jsonrpc": "2.0", "id": body["id"]}
        if self.server.reject and body["method"] != "device.info":
            response["error"] = {"message": "Touch rejected"}
        else:
            response["result"] = result
        data = json.dumps(response).encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


@pytest.fixture
def devicekit():
    server = HTTPServer(("127.0.0.1", 0), Handler)
    server.calls = []
    server.reject = False
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    client = DeviceKitSwipeClient(f"http://127.0.0.1:{server.server_port}")
    try:
        yield client, server
    finally:
        client.close()
        server.shutdown()
        server.server_close()
        thread.join()


def test_four_directions_have_release_and_correct_axis(devicekit):
    client, server = devicekit
    client.start()
    for direction, axis, sign in (
        ("LEFT", "x", -1),
        ("RIGHT", "x", 1),
        ("HOP", "y", -1),
        ("DUCK", "y", 1),
    ):
        assert client.native_swipe(direction) >= 0
        actions = server.calls[-1]["params"]["actions"]
        assert [a["type"] for a in actions] == ["press", "move", "release"]
        assert sign * (actions[1][axis] - actions[0][axis]) > 0
        assert (
            actions[1]["x" if axis == "y" else "y"]
            == actions[0]["x" if axis == "y" else "y"]
        )
        assert actions[2]["x"] == actions[1]["x"]
        assert actions[2]["y"] == actions[1]["y"]
    assert [call["method"] for call in server.calls] == ["device.info"] + [
        "device.io.gesture"
    ] * 4


def test_rejected_gesture_is_not_retried(devicekit):
    client, server = devicekit
    client.start()
    server.reject = True
    with pytest.raises(RuntimeError, match="Touch rejected"):
        client.native_swipe("LEFT")
    assert len(server.calls) == 2


def test_invalid_direction_does_not_contact_helper(devicekit):
    client, server = devicekit
    with pytest.raises(ValueError):
        client.native_swipe("UNKNOWN")
    assert server.calls == []


def test_fast_backend_prepares_once_and_sends_small_direction_request(devicekit):
    _client, server = devicekit
    fast = FastDeviceKitSwipeClient(f"http://127.0.0.1:{server.server_port}")
    try:
        fast.start()
        fast.native_swipe("STEP_L")
        fast.native_swipe("HOP")
        assert [call["method"] for call in server.calls] == [
            "device.info",
            "device.io.fastSwipe.prepare",
            "device.io.fastSwipe",
            "device.io.fastSwipe",
        ]
        assert [call["params"] for call in server.calls[2:]] == [
            {"direction": "left"},
            {"direction": "up"},
        ]
    finally:
        fast.close()
