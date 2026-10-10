"""Crouch follows hip-to-ankle span, not shoulder image height."""

import pose_controller as pt

ASPECT = 640 / 480


class Lm:
    def __init__(self, x, y, visibility=1.0):
        self.x = x
        self.y = y
        self.visibility = visibility


def body(hip_y=0.55, ankle_y=0.90, scale=1.0, ankle_vis=1.0, y_shift=0.0):
    center = 0.5
    span_scale = scale

    def px(v):
        return center + scale * (v - center)

    def py(v):
        return y_shift + center + span_scale * (v - center)

    half = 0.10 * scale
    pts = [Lm(0.5, 0.5) for _ in range(33)]
    pts[pt.LSH] = Lm(center - half, py(0.30))
    pts[pt.RSH] = Lm(center + half, py(0.30))
    pts[pt.LHIP] = Lm(px(0.42), py(hip_y))
    pts[pt.RHIP] = Lm(px(0.58), py(hip_y))
    pts[pt.LANK] = Lm(px(0.42), py(ankle_y), ankle_vis)
    pts[pt.RANK] = Lm(px(0.58), py(ankle_y), ankle_vis)
    return pts


def width(lm):
    return abs(lm[pt.LSH].x - lm[pt.RSH].x) * ASPECT


def measure(lm, neutral):
    return pt.crouch_measurement(lm, width(lm), neutral)


def test_upright_at_calibration_scale_is_not_a_crouch():
    upright = body()
    neutral = pt.leg_ratio(upright, width(upright))
    value = measure(upright, neutral)
    assert abs(value) < 1e-9
    holding, event = pt.crouch_update(False, value)
    assert event is None
    assert holding is False
    shifted = body(y_shift=0.20)
    assert abs(measure(shifted, neutral)) < 1e-9


def test_upright_scaled_smaller_is_not_a_crouch():
    neutral = pt.leg_ratio(body(), width(body()))
    value = measure(body(scale=0.45), neutral)
    assert abs(value) < 1e-9
    _holding, event = pt.crouch_update(False, value)
    assert event is None


def test_upright_scaled_larger_is_not_a_crouch():
    neutral = pt.leg_ratio(body(), width(body()))
    value = measure(body(scale=1.8), neutral)
    assert abs(value) < 1e-9
    _holding, event = pt.crouch_update(False, value)
    assert event is None


def test_crouch_at_calibration_scale():
    neutral = pt.leg_ratio(body(), width(body()))
    value = measure(body(hip_y=0.78), neutral)
    assert value > pt.DUCK[0]
    holding, event = pt.crouch_update(False, value)
    assert event == "DUCK"
    assert holding is True


def test_equivalent_crouch_scaled_smaller():
    neutral = pt.leg_ratio(body(), width(body()))
    full = measure(body(hip_y=0.78), neutral)
    far = measure(body(hip_y=0.78, scale=0.45), neutral)
    assert abs(far - full) < 1e-9
    _holding, event = pt.crouch_update(False, far)
    assert event == "DUCK"


def test_equivalent_crouch_scaled_larger():
    neutral = pt.leg_ratio(body(), width(body()))
    full = measure(body(hip_y=0.78), neutral)
    close = measure(body(hip_y=0.78, scale=1.7), neutral)
    assert abs(close - full) < 1e-9
    _holding, event = pt.crouch_update(False, close)
    assert event == "DUCK"


def test_held_crouch_does_not_repeat():
    neutral = pt.leg_ratio(body(), width(body()))
    value = measure(body(hip_y=0.78), neutral)
    holding, event = pt.crouch_update(False, value)
    assert event == "DUCK"
    holding, event = pt.crouch_update(holding, value)
    assert event is None
    assert holding is True


def test_returning_upright_releases_crouch():
    neutral = pt.leg_ratio(body(), width(body()))
    holding, _event = pt.crouch_update(False, measure(body(hip_y=0.78), neutral))
    value = measure(body(scale=0.6), neutral)
    holding, event = pt.crouch_update(holding, value)
    assert event is None
    assert holding is False


def test_missing_leg_landmarks_do_not_crouch():
    neutral = pt.leg_ratio(body(), width(body()))
    hidden = body(ankle_vis=0.2)
    assert pt.legs_visible(hidden) is False
    assert measure(hidden, neutral) is None
