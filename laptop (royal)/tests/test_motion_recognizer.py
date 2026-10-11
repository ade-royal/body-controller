"""Action sequences, rejection and tracking recovery without a camera."""

from types import SimpleNamespace

import pose_controller as pt
import pytest


def body(
    dx=0.0,
    up=0.0,
    hip_drop=0.0,
    shoulder_drop=0.0,
    foot_up=None,
    lean=0.0,
    scale=1.0,
    feet=True,
    width_scale=1.0,
):
    """Synthetic projected body; up is whole-body travel in torso lengths."""
    torso = 0.25
    foot_up = up if foot_up is None else foot_up
    points = [SimpleNamespace(x=0.5, y=0.5, visibility=1.0) for _ in range(33)]

    def point(x, y, visible=1.0):
        return SimpleNamespace(
            x=0.5 + scale * (x - 0.5), y=0.5 + scale * (y - 0.5), visibility=visible
        )

    points[pt.LSH] = point(
        0.4 * width_scale + 0.5 * (1 - width_scale) + dx + lean,
        0.30 - up * torso + shoulder_drop,
    )
    points[pt.RSH] = point(
        0.6 * width_scale + 0.5 * (1 - width_scale) + dx + lean,
        0.30 - up * torso + shoulder_drop,
    )
    points[pt.LHIP] = point(0.42 + dx, 0.55 - up * torso + hip_drop)
    points[pt.RHIP] = point(0.58 + dx, 0.55 - up * torso + hip_drop)
    points[pt.LANK] = point(0.42 + dx, 0.90 - foot_up * torso, 1.0 if feet else 0.2)
    points[pt.RANK] = point(0.58 + dx, 0.90 - foot_up * torso, 1.0 if feet else 0.2)
    return points


def make_recognizer(scale=1.0, feet=True):
    lm = body(scale=scale, feet=feet)
    base = pt.features(lm, 1.0)
    base["leg"] = pt.leg_ratio(lm, base["sw"]) if feet else None
    base["ay"] = (lm[pt.LANK].y + lm[pt.RANK].y) / 2 if feet else None
    return pt.MotionRecognizer(base)


class Player:
    def __init__(self, scale=1.0, feet=True, fps=30):
        self.recognizer = make_recognizer(scale, feet)
        self.scale, self.feet = scale, feet
        self.time = 0.0
        self.frame = 1 / fps
        self.events = []
        self.hold(0.4)

    def sample(self, lm):
        out = self.recognizer.update(lm, self.time, 1.0)
        self.time += self.frame
        self.events.extend(out["events"])
        assert out["lean_held"] is None
        return out

    def hold(self, seconds, **kwargs):
        for _ in range(round(seconds / self.frame)):
            self.sample(body(scale=self.scale, feet=self.feet, **kwargs))

    def motion(self, seconds, start, end):
        frames = round(seconds / self.frame)
        for i in range(1, frames + 1):
            values = {k: v + (end[k] - v) * i / frames for k, v in start.items()}
            self.sample(body(scale=self.scale, feet=self.feet, **values))

    def jump(self, dx=0.0):
        self.motion(0.20, {"up": 0.0, "dx": dx}, {"up": 0.55, "dx": dx})
        self.motion(0.20, {"up": 0.55, "dx": dx}, {"up": 0.0, "dx": dx})
        self.hold(0.15, dx=dx)


@pytest.mark.parametrize("scale", [0.5, 1.0, 1.8])
@pytest.mark.parametrize("fps", [20, 30, 60])
def test_jump_fires_once_across_body_sizes_and_frame_rates(scale, fps):
    player = Player(scale=scale, fps=fps)
    player.jump()
    assert player.events == ["HOP"]


def test_second_jump_after_landing_counts():
    player = Player()
    player.jump()
    player.jump()
    assert player.events == ["HOP", "HOP"]


def test_long_airborne_pose_does_not_retrigger_after_cooldown():
    player = Player()
    player.motion(0.2, {"up": 0.0}, {"up": 0.5})
    player.hold(0.7, up=0.5)
    player.motion(0.15, {"up": 0.5}, {"up": 0.8})
    player.hold(0.4, up=0.8)
    assert player.events == ["HOP"]


def test_jump_with_small_sideways_wobble_emits_only_jump():
    player = Player()
    player.motion(0.2, {"up": 0.0, "dx": 0.0}, {"up": 0.5, "dx": 0.02})
    player.motion(0.2, {"up": 0.5, "dx": 0.02}, {"up": 0.0, "dx": 0.0})
    player.hold(0.3)
    assert player.events == ["HOP"]


def test_jump_then_deliberate_right_while_airborne_preserves_order():
    player = Player()
    player.motion(0.2, {"up": 0.0}, {"up": 0.5})
    player.motion(0.25, {"up": 0.5, "dx": 0.0}, {"up": 0.5, "dx": 0.2})
    assert player.events == ["HOP", "STEP_RIGHT"]


def test_crouch_then_fast_standing_and_overshoot_is_not_jump():
    player = Player()
    player.motion(
        0.25,
        {"hip_drop": 0.0, "shoulder_drop": 0.0},
        {"hip_drop": 0.18, "shoulder_drop": 0.12},
    )
    player.hold(0.3, hip_drop=0.18, shoulder_drop=0.12)
    player.motion(
        0.2,
        {"hip_drop": 0.18, "shoulder_drop": 0.12},
        {"hip_drop": -0.04, "shoulder_drop": -0.04},
    )
    player.hold(0.3)
    assert player.events == ["DUCK"]
    assert player.recognizer.crouch_held is False


def test_real_jump_after_crouch_recovery_can_count():
    player = Player()
    player.motion(
        0.2,
        {"hip_drop": 0.0, "shoulder_drop": 0.0},
        {"hip_drop": 0.18, "shoulder_drop": 0.12},
    )
    player.hold(0.15, hip_drop=0.18, shoulder_drop=0.12)
    player.motion(
        0.15,
        {"hip_drop": 0.18, "shoulder_drop": 0.12},
        {"hip_drop": 0.0, "shoulder_drop": 0.0},
    )
    player.jump()
    assert player.events == ["DUCK", "HOP"]


def test_lateral_body_bob_with_grounded_feet_is_not_jump():
    player = Player()
    player.motion(
        0.25,
        {"dx": 0.0, "up": 0.0, "foot_up": 0.0},
        {"dx": -0.2, "up": 0.18, "foot_up": 0.0},
    )
    player.hold(0.2, dx=-0.2, up=0.18, foot_up=0.0)
    assert player.events == ["STEP_LEFT"]


def test_one_frame_vertical_spike_is_rejected():
    player = Player()
    player.sample(body(up=0.1, foot_up=0.0))
    player.hold(0.3)
    assert player.events == []


def test_lean_and_shoulder_width_change_produce_no_input():
    player = Player()
    player.hold(0.4, lean=-0.05, width_scale=0.3)
    player.hold(0.4, lean=0.05, width_scale=0.3)
    assert player.events == []


def test_tracking_loss_releases_crouch_and_reacquisition_does_not_step():
    player = Player()
    player.hold(0.3, hip_drop=0.18, shoulder_drop=0.12)
    assert player.recognizer.crouch_held
    out = player.sample(None)
    assert out == {"events": [], "lean_held": None, "crouch_held": False}
    player.hold(0.3, dx=0.3)
    assert player.events == ["DUCK"]


def test_tracking_loss_mid_jump_does_not_retrigger_on_reacquisition():
    player = Player()
    player.motion(0.2, {"up": 0.0}, {"up": 0.4})
    player.sample(None)
    player.motion(0.2, {"up": 0.4}, {"up": 0.8})
    assert player.events == ["HOP"]


def test_long_frame_gap_cannot_turn_position_change_into_input():
    player = Player()
    player.time += 0.5
    player.hold(0.3, dx=0.3, up=0.2)
    assert player.events == []


def test_low_confidence_core_landmarks_reset_motion():
    player = Player()
    lm = body(dx=0.5, up=0.8)
    lm[pt.LHIP].visibility = 0.1
    assert player.sample(lm)["events"] == []


def test_hidden_feet_require_larger_coordinated_rise():
    player = Player(feet=False)
    player.motion(0.2, {"up": 0.0}, {"up": 0.15})
    player.hold(0.3, up=0.15)
    assert player.events == []


def test_hidden_feet_can_recognize_clear_jump():
    player = Player(feet=False)
    player.jump()
    assert player.events == ["HOP"]


def test_stable_scale_ignores_turning_shoulder_width():
    player = Player()
    original = player.recognizer.width
    player.hold(0.7, width_scale=0.25)
    assert player.recognizer.width == pytest.approx(original)


def test_nonfinite_landmark_values_do_not_create_events():
    player = Player()
    lm = body()
    lm[pt.LHIP].x = float("nan")
    assert player.sample(lm)["events"] == []


def test_crouch_reacquisition_does_not_retrigger_same_action():
    player = Player()
    player.hold(0.3, hip_drop=0.18, shoulder_drop=0.12)
    player.sample(None)
    player.hold(0.3, hip_drop=0.18, shoulder_drop=0.12)
    assert player.events == ["DUCK"]


def test_brief_missing_feet_releases_hold_without_duplicate_crouch():
    player = Player()
    player.hold(0.3, hip_drop=0.18, shoulder_drop=0.12)
    out = player.sample(body(hip_drop=0.18, shoulder_drop=0.12, feet=False))
    assert out["crouch_held"] is False
    player.hold(0.3, hip_drop=0.18, shoulder_drop=0.12)
    assert player.events == ["DUCK"]
    assert player.recognizer.crouch_held is True


def test_two_crouches_with_a_standing_interval_count_twice():
    player = Player()
    player.hold(0.3, hip_drop=0.18, shoulder_drop=0.12)
    player.hold(0.3)
    player.hold(0.3, hip_drop=0.18, shoulder_drop=0.12)
    assert player.events == ["DUCK", "DUCK"]


def test_cropped_ankles_are_not_used_as_takeoff_evidence():
    lm = body(scale=1.8)
    assert pt.legs_visible(lm)
    assert not pt.feet_observed(lm)
