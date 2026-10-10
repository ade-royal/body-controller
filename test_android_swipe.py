import struct

from android_pose import AndroidOutput
from android_swipe import (
    ACTION_DOWN,
    ACTION_UP,
    POINTER_ID,
    swipe_points,
    touch_message,
)


def test_touch_message_matches_scrcpy_v5_layout():
    message = touch_message(ACTION_DOWN, 450, 800, 900, 1600)
    assert len(message) == 32
    fields = struct.unpack(">BBqiiHHHii", message)
    assert fields == (2, ACTION_DOWN, POINTER_ID, 450, 800, 900, 1600, 0xFFFF, 0, 0)


def test_touch_up_releases_pressure():
    assert struct.unpack(">BBqiiHHHii", touch_message(ACTION_UP, 1, 2, 3, 4))[7] == 0


def test_swipes_start_at_center_and_move_one_way():
    for direction, (dx, dy) in {"LEFT": (-1, 0), "RIGHT": (1, 0), "UP": (0, -1), "DOWN": (0, 1)}.items():
        points = swipe_points(direction, 900, 1600)
        assert points[0] == (450, 800)
        end_x, end_y = points[-1]
        assert (end_x - 450) * dx >= 0 and (end_y - 800) * dy >= 0
        assert points[-1] != points[0]


def test_dry_run_output_maps_body_events_to_swipes():
    output = AndroidOutput("unused", dry_run=True)
    output.start()
    output.submit_frame({"events": ["STEP_L", "HOP", "DUCK"]})
    output.close()
    assert output.sent == 3
