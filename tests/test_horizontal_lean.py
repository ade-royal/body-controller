"""LEFT/RIGHT follows torso shape relative to the calibrated stance."""

import pose_test as pt

ASPECT = 640 / 480
SHOULDER_WIDTH = 0.20


class Lm:
    def __init__(self, x, y):
        self.x = x
        self.y = y
        self.visibility = 1.0


def landmarks(shoulder_x, hip_x, dx=0.0, sw=SHOULDER_WIDTH):
    pts = [Lm(0.0, 0.0) for _ in range(33)]
    pts[pt.LSH] = Lm(shoulder_x - sw / 2 + dx, 0.30)
    pts[pt.RSH] = Lm(shoulder_x + sw / 2 + dx, 0.30)
    pts[pt.LHIP] = Lm(hip_x - 0.08 + dx, 0.60)
    pts[pt.RHIP] = Lm(hip_x + 0.08 + dx, 0.60)
    return pts


def feat(shoulder_x, hip_x, dx=0.0, sw=SHOULDER_WIDTH):
    return pt.features(landmarks(shoulder_x, hip_x, dx, sw=sw), ASPECT)


def scaled_pose(shoulder_x, hip_x, scale, center=0.5):
    """Same torso geometry, drawn at a closer or farther camera scale."""
    def project(x):
        return center + scale * (x - center)

    return feat(project(shoulder_x), project(hip_x), sw=SHOULDER_WIDTH * scale)


def direction(state):
    return "NEUTRAL" if state is None else pt.KEY[state]


def update(state, frame, base):
    lean, _lean_old, _hip_x = pt.horizontal_signals(frame, base)
    return pt.hysteresis(state, lean, *pt.LEAN, "STEP_L", "STEP_R")


def test_calibrated_upright_pose_is_neutral():
    base = pt.average_baseline([feat(0.50, 0.50), feat(0.50, 0.50)])
    assert direction(update(None, feat(0.50, 0.50), base)) == "NEUTRAL"


def test_same_upright_body_translated_left_is_neutral():
    base = feat(0.50, 0.50)
    moved = feat(0.50, 0.50, dx=-0.15)
    lean, _lean_old, hip_x = pt.horizontal_signals(moved, base)
    assert abs(lean) < pt.LEAN[1]
    assert hip_x <= -0.5  # old image-position signal would have been LEFT
    assert direction(update(None, moved, base)) == "NEUTRAL"


def test_same_upright_body_translated_right_is_neutral():
    base = feat(0.50, 0.50)
    moved = feat(0.50, 0.50, dx=0.15)
    lean, _lean_old, hip_x = pt.horizontal_signals(moved, base)
    assert abs(lean) < pt.LEAN[1]
    assert hip_x >= 0.5  # old image-position signal would have been RIGHT
    assert direction(update(None, moved, base)) == "NEUTRAL"


def test_left_leaning_torso_is_left():
    base = feat(0.50, 0.50)
    # Shoulders move left of the hips by 0.05; shoulder width is 0.20 → lean -0.25.
    assert direction(update(None, feat(0.45, 0.50), base)) == "LEFT"


def test_right_leaning_torso_is_right():
    base = feat(0.50, 0.50)
    assert direction(update(None, feat(0.55, 0.50), base)) == "RIGHT"


def test_held_lean_remains_while_the_body_shifts():
    base = feat(0.50, 0.50)
    state = update(None, feat(0.45, 0.50), base)
    assert direction(state) == "LEFT"
    state = update(state, feat(0.45, 0.50), base)
    assert direction(state) == "LEFT"
    state = update(state, feat(0.45, 0.50, dx=0.20), base)
    assert direction(state) == "LEFT"


def test_returning_upright_after_moving_elsewhere_is_neutral():
    base = feat(0.50, 0.50)
    state = update(None, feat(0.55, 0.50), base)
    assert direction(state) == "RIGHT"
    state = update(state, feat(0.50, 0.50, dx=-0.18), base)
    assert direction(state) == "NEUTRAL"


def test_neutral_need_not_stack_shoulders_on_hips():
    base = pt.average_baseline([feat(0.52, 0.50), feat(0.52, 0.50)])
    assert direction(update(None, feat(0.52, 0.50, dx=-0.12), base)) == "NEUTRAL"
    assert direction(update(None, feat(0.57, 0.50), base)) == "RIGHT"


def test_hysteresis_holds_between_enter_and_release():
    base = feat(0.50, 0.50)
    state = update(None, feat(0.45, 0.50), base)  # lean -0.25, past enter
    assert direction(state) == "LEFT"
    state = update(state, feat(0.47, 0.50), base)  # lean -0.15, still past release
    assert direction(state) == "LEFT"
    assert direction(update(None, feat(0.47, 0.50), base)) == "NEUTRAL"
    state = update(state, feat(0.48, 0.50), base)  # lean -0.10, inside release
    assert direction(state) == "NEUTRAL"


def _lean(frame, base):
    lean, lean_old, _hip_x = pt.horizontal_signals(frame, base)
    return lean, lean_old


def test_neutral_pose_at_calibration_scale_is_neutral():
    base = feat(0.52, 0.50)
    lean, _old = _lean(scaled_pose(0.52, 0.50, 1.0), base)
    assert abs(lean) < 1e-9
    assert direction(update(None, scaled_pose(0.52, 0.50, 1.0), base)) == "NEUTRAL"


def test_same_neutral_pose_scaled_smaller_is_neutral():
    base = feat(0.52, 0.50)
    pose = scaled_pose(0.52, 0.50, 0.45)
    lean, lean_old = _lean(pose, base)
    assert abs(lean) < 1e-9
    assert lean_old < -0.05
    assert direction(update(None, pose, base)) == "NEUTRAL"


def test_same_neutral_pose_scaled_larger_is_neutral():
    base = feat(0.52, 0.50)
    pose = scaled_pose(0.52, 0.50, 1.8)
    lean, lean_old = _lean(pose, base)
    assert abs(lean) < 1e-9
    assert lean_old > 0.05
    assert direction(update(None, pose, base)) == "NEUTRAL"


def test_left_lean_at_calibration_scale_is_left():
    base = feat(0.50, 0.50)
    pose = scaled_pose(0.45, 0.50, 1.0)
    lean, _old = _lean(pose, base)
    assert abs(lean - -0.25) < 1e-9
    assert direction(update(None, pose, base)) == "LEFT"


def test_same_left_lean_scaled_smaller_stays_left():
    base = feat(0.50, 0.50)
    full = scaled_pose(0.45, 0.50, 1.0)
    far = scaled_pose(0.45, 0.50, 0.45)
    lean_full, old_full = _lean(full, base)
    lean_far, old_far = _lean(far, base)
    assert abs(lean_far - lean_full) < 1e-9
    assert lean_far <= -pt.LEAN[0]
    assert old_far > -pt.LEAN[1]
    state = update(None, full, base)
    assert direction(state) == "LEFT"
    state = update(state, far, base)
    assert direction(state) == "LEFT"


def test_same_left_lean_scaled_larger_matches():
    base = feat(0.50, 0.50)
    full = scaled_pose(0.45, 0.50, 1.0)
    close = scaled_pose(0.45, 0.50, 1.7)
    lean_full, _old_full = _lean(full, base)
    lean_close, old_close = _lean(close, base)
    assert abs(lean_close - lean_full) < 1e-9
    assert old_close < lean_close
    assert direction(update(None, close, base)) == "LEFT"


def test_right_lean_at_calibration_scale_is_right():
    base = feat(0.50, 0.50)
    pose = scaled_pose(0.55, 0.50, 1.0)
    lean, _old = _lean(pose, base)
    assert abs(lean - 0.25) < 1e-9
    assert direction(update(None, pose, base)) == "RIGHT"


def test_same_right_lean_scaled_smaller_stays_right():
    base = feat(0.50, 0.50)
    full = scaled_pose(0.55, 0.50, 1.0)
    far = scaled_pose(0.55, 0.50, 0.45)
    lean_full, old_full = _lean(full, base)
    lean_far, old_far = _lean(far, base)
    assert abs(lean_far - lean_full) < 1e-9
    assert lean_far >= pt.LEAN[0]
    assert old_far < pt.LEAN[1]
    state = update(None, full, base)
    assert direction(state) == "RIGHT"
    state = update(state, far, base)
    assert direction(state) == "RIGHT"


def test_same_right_lean_scaled_larger_matches():
    base = feat(0.50, 0.50)
    full = scaled_pose(0.55, 0.50, 1.0)
    close = scaled_pose(0.55, 0.50, 1.7)
    lean_full, _old_full = _lean(full, base)
    lean_close, _old_close = _lean(close, base)
    assert abs(lean_close - lean_full) < 1e-9
    assert direction(update(None, close, base)) == "RIGHT"


def test_return_to_neutral_geometry_clears_the_lean():
    base = feat(0.50, 0.50)
    state = update(None, scaled_pose(0.45, 0.50, 1.0), base)
    assert direction(state) == "LEFT"
    state = update(state, scaled_pose(0.50, 0.50, 0.6), base)
    assert direction(state) == "NEUTRAL"
    state = update(None, scaled_pose(0.55, 0.50, 1.4), base)
    assert direction(state) == "RIGHT"
    state = update(state, scaled_pose(0.50, 0.50, 1.4), base)
    assert direction(state) == "NEUTRAL"
