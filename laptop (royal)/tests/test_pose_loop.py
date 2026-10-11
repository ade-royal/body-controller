"""Exercise actual camera-loop wiring without a camera or external inputs."""

from types import SimpleNamespace

import numpy as np
import pose_controller as pt
import pytest
from test_motion_recognizer import body


@pytest.mark.parametrize("fail_callback", [False, True])
def test_camera_loop_calibrates_delivers_actions_and_releases_resources(
    monkeypatch, fail_callback
):
    class Capture:
        def __init__(self):
            self.index = -1
            self.released = False

        def set(self, *_):
            pass

        def isOpened(self):
            return True

        def read(self):
            self.index += 1
            return (self.index < 160, np.zeros((480, 640, 3), dtype=np.uint8))

        def release(self):
            self.released = True

    cap = Capture()

    class Detector:
        closed = False

        def detect_for_video(self, *_):
            dx = max(0, min(0.20, (cap.index - 125) / 30 * 0.8))
            return SimpleNamespace(pose_landmarks=[body(dx=dx)])

        def close(self):
            self.closed = True

    detector = Detector()
    monkeypatch.setattr(pt.cv2, "VideoCapture", lambda *_: cap)
    monkeypatch.setattr(
        pt.vision.PoseLandmarker, "create_from_options", lambda *_: detector
    )
    monkeypatch.setattr(pt.time, "perf_counter", lambda: max(0, cap.index) / 30)
    monkeypatch.setattr(pt.cv2, "imshow", lambda *_: None)
    monkeypatch.setattr(
        pt.cv2, "waitKey", lambda *_: ord("c") if cap.index == 0 else -1
    )
    monkeypatch.setattr(pt.cv2, "destroyAllWindows", lambda: None)
    outputs = []

    def callback(frame):
        outputs.append(frame)
        if fail_callback and frame["events"]:
            raise RuntimeError("fake output failure")

    if fail_callback:
        with pytest.raises(RuntimeError, match="fake output failure"):
            pt.main(callback)
    else:
        pt.main(callback)
    assert [event for frame in outputs for event in frame["events"]] == ["STEP_RIGHT"]
    assert all(frame["lean_held"] is None for frame in outputs)
    assert outputs[-1] == {"events": [], "lean_held": None, "crouch_held": False}
    assert cap.released
    assert detector.closed
