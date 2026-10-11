"""Lateral travel includes deliberate reversals and rejects small motion."""

import pose_controller as pt
import pytest


class Travel:
    def __init__(self, scale=1.0, fps=30):
        self.motion = pt.LateralMotion()
        self.width = 0.2 * scale
        self.time = 0.0
        self.frame = 1 / fps
        self.position = 0.0
        self.events = []
        self.sample(0.0)

    def sample(self, position, shoulder_position=None):
        shoulder_position = position if shoulder_position is None else shoulder_position
        event = self.motion.update(
            0.5 + position * self.width,
            0.5 + shoulder_position * self.width,
            self.time,
            self.width,
        )
        self.time += self.frame
        self.position = position
        if event:
            self.events.append(event)

    def move(self, end, seconds=0.3):
        start = self.position
        frames = round(seconds / self.frame)
        for i in range(1, frames + 1):
            self.sample(start + (end - start) * i / frames)

    def hold(self, seconds=0.4):
        for _ in range(round(seconds / self.frame)):
            self.sample(self.position)


@pytest.mark.parametrize("sign,event", [(-1, "STEP_LEFT"), (1, "STEP_RIGHT")])
@pytest.mark.parametrize("scale", [0.5, 1.0, 1.8])
@pytest.mark.parametrize("fps", [20, 30, 60])
def test_meaningful_travel_fires_once_across_sizes_and_frame_rates(
    sign, event, scale, fps
):
    travel = Travel(scale, fps)
    travel.move(sign * 0.8)
    travel.move(sign * 1.6)
    assert travel.events == [event]


@pytest.mark.parametrize("sign", [-1, 1])
def test_immediate_deliberate_reversal_counts_without_neutral_pause(sign):
    travel = Travel()
    travel.move(sign * 0.8)
    travel.move(0.0)
    expected = ["STEP_RIGHT", "STEP_LEFT"] if sign > 0 else ["STEP_LEFT", "STEP_RIGHT"]
    assert travel.events == expected


def test_second_same_direction_action_counts_after_stopping():
    travel = Travel()
    travel.move(-0.8)
    travel.hold()
    travel.move(-1.6)
    assert travel.events == ["STEP_LEFT", "STEP_LEFT"]


def test_small_fast_wobble_does_not_count():
    travel = Travel()
    for _ in range(10):
        travel.sample(0.05)
        travel.sample(-0.05)
    assert travel.events == []


def test_single_large_spike_without_sustained_motion_does_not_count():
    travel = Travel()
    travel.sample(0.5)
    travel.sample(0.0)
    travel.hold()
    assert travel.events == []


def test_shoulder_tilt_without_hip_translation_does_not_count():
    travel = Travel()
    for i in range(12):
        travel.sample(0.0, i * 0.06)
    assert travel.events == []


def test_hip_wobble_without_shoulder_travel_does_not_count():
    travel = Travel()
    for i in range(12):
        travel.sample(i * 0.06, 0.0)
    assert travel.events == []


def test_small_reverse_does_not_rearm_or_fire():
    travel = Travel()
    travel.move(0.8)
    travel.move(0.7, seconds=0.1)
    travel.move(1.4)
    assert travel.events == ["STEP_RIGHT"]


def test_standing_elsewhere_is_neutral():
    travel = Travel()
    travel.position = 3.0
    travel.motion = pt.LateralMotion()
    travel.hold()
    assert travel.events == []
