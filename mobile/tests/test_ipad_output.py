import threading

import pytest

from mobile.ipad_output import IpadOutput, frame_directions


class Client:
    def __init__(self, url):
        self.calls = []
        self.closed = False
        self.entered = threading.Event()
        self.release = threading.Event()
        self.release.set()
        self.fail = False

    def start(self):
        pass

    def native_swipe(self, direction):
        self.calls.append(direction)
        self.entered.set()
        assert self.release.wait(2)
        if self.fail:
            raise RuntimeError("Touch failed")
        return 400

    def close(self):
        self.closed = True


def wait_idle(output):
    with output.condition:
        assert output.condition.wait_for(lambda: not output.busy, timeout=2)


def test_friend_event_names_map_to_all_four_swipes():
    assert frame_directions({"events": ["STEP_L", "STEP_R", "HOP", "DUCK"]}) == [
        "LEFT",
        "RIGHT",
        "UP",
        "DOWN",
    ]
    assert frame_directions({"events": ["STEP_LEFT", "STEP_RIGHT"]}) == [
        "LEFT",
        "RIGHT",
    ]


def test_held_pose_never_repeats_and_same_direction_is_deduplicated():
    assert (
        frame_directions({"events": [], "lean_held": "STEP_L", "crouch_held": True})
        == []
    )
    assert frame_directions({"events": ["STEP_L", "STEP_LEFT", "PRIMARY_GESTURE"]}) == [
        "LEFT"
    ]


def test_worker_delivers_directions_and_closes_connection():
    client = Client("")
    output = IpadOutput(client_factory=lambda url: client)
    output.start()
    try:
        for event in ("left", "right", "HOP", "DUCK"):
            assert output.submit(event)
            wait_idle(output)
        assert client.calls == ["LEFT", "RIGHT", "UP", "DOWN"]
        assert output.sent == 4
    finally:
        output.close()
    assert client.closed
    assert not output.thread.is_alive()


def test_slow_touch_does_not_block_detector_or_build_a_backlog():
    client = Client("")
    client.release.clear()
    output = IpadOutput(client_factory=lambda url: client)
    output.start()
    try:
        assert output.submit("LEFT")
        assert client.entered.wait(2)
        # The fake touch is still blocked; submissions complete independently.
        assert not output.submit("RIGHT")
        output.submit_frame({"events": ["HOP", "DUCK"]})
        assert output.skipped == 3
        assert client.calls == ["LEFT"]
        client.release.set()
        wait_idle(output)
        assert output.pending is None
        assert output.submit("UP")
        wait_idle(output)
        assert client.calls == ["LEFT", "UP"]
    finally:
        client.release.set()
        output.close()


def test_swipe_failure_stops_output_without_retry():
    client = Client("")
    client.fail = True
    output = IpadOutput(client_factory=lambda url: client)
    output.start()
    try:
        output.submit("DOWN")
        wait_idle(output)
        assert output.error == "Touch failed"
        assert not output.submit("UP")
        assert client.calls == ["DOWN"]
    finally:
        output.close()


def test_startup_failure_is_reported_before_camera_launch():
    client = Client("")

    def fail():
        raise RuntimeError("Helper unavailable")

    client.start = fail
    output = IpadOutput(client_factory=lambda url: client)
    with pytest.raises(RuntimeError, match="Helper unavailable"):
        output.start()
    assert client.closed


def test_dry_run_never_creates_device_client():
    def forbidden(url):
        pytest.fail("Dry run opened a device connection")

    output = IpadOutput(dry_run=True, client_factory=forbidden)
    output.start()
    try:
        output.submit_frame({"events": ["STEP_R"]})
        wait_idle(output)
        assert output.sent == 1
    finally:
        output.close()
