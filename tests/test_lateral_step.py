"""STEP_LEFT / STEP_RIGHT are one-shot lateral movements, then neutral."""

import collections

import pose_test as pt

ASPECT = 640 / 480
SHOULDER_WIDTH = 0.20
LEFT = -(pt.STEP_V[0] + 0.25)
RIGHT = pt.STEP_V[0] + 0.25
FRAME = 1 / 30


def drive(state, speed, dt=FRAME):
    return pt.step_update(state, speed, dt)


def phase(state):
    return pt.step_label(state)


def settle(state):
    """Hold a quiet speed for one full settle window."""
    return pt.step_update(state, 0.0, pt.STEP_WINDOW)


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


def pose_at_scale(physical_dx, scale, center=0.5):
    """Upright body at a camera scale, hips shifted in calibration-scale units."""
    return feat(center, center + scale * physical_dx, sw=SHOULDER_WIDTH * scale)


def step_speeds(history, frame, now, base):
    """Live step speed, then the old calibrated-shoulder-width speed."""
    x0, win_dt = pt.hip_window(history, frame["hx"], now)
    live = pt.lateral_speed(x0, frame["hx"], win_dt, frame["sw"])
    old = pt.lateral_speed(x0, frame["hx"], win_dt, base["sw"])
    return live, old


def test_stationary_person_emits_no_step():
    state, event = drive(None, 0.0)
    assert event is None
    assert state is None
    assert phase(state) == "NEUTRAL"


def test_lateral_movement_left_emits_one_step_left():
    state, event = drive(None, LEFT)
    assert event == "STEP_LEFT"
    assert phase(state) == "MOVING_LEFT"


def test_continued_leftward_movement_does_not_repeat():
    state, event = drive(None, LEFT)
    assert event == "STEP_LEFT"
    for _ in range(10):
        state, event = drive(state, LEFT)
        assert event is None
        assert phase(state) == "MOVING_LEFT"


def test_movement_stop_returns_to_neutral():
    state, _event = drive(None, LEFT)
    state, event = drive(state, 0.0)
    assert event is None
    assert phase(state) == "RECOVER_LEFT"
    state, event = settle(state)
    assert event is None
    assert state is None
    assert phase(state) == "NEUTRAL"


def test_another_leftward_movement_emits_again():
    state, _event = drive(None, LEFT)
    state, _event = settle(state)
    state, event = drive(state, LEFT)
    assert event == "STEP_LEFT"
    assert phase(state) == "MOVING_LEFT"


def test_lateral_movement_right_emits_step_right():
    state, event = drive(None, RIGHT)
    assert event == "STEP_RIGHT"
    assert phase(state) == "MOVING_RIGHT"
    state, event = drive(state, RIGHT)
    assert event is None
    state, event = drive(state, 0.0)
    assert event is None
    assert phase(state) == "RECOVER_RIGHT"
    state, event = settle(state)
    assert event is None
    assert state is None


def test_standing_at_a_different_horizontal_position_emits_no_step():
    base = feat(0.50, 0.50)
    parked = feat(0.50, 0.50, dx=0.30)
    history = collections.deque()
    first = pt.track_lateral_speed(history, parked["hx"], 0.0, base["sw"])
    later = pt.track_lateral_speed(history, parked["hx"], pt.STEP_WINDOW, base["sw"])
    assert first == 0.0
    assert later == 0.0
    state, event = drive(None, later)
    assert event is None
    assert state is None


def test_torso_lean_without_hip_translation_emits_no_step():
    base = feat(0.50, 0.50)
    leaned = feat(0.45, 0.50)
    speed = pt.lateral_speed(base["hx"], leaned["hx"], pt.STEP_WINDOW, base["sw"])
    assert abs(speed) < pt.STEP_V[1]
    _state, event = drive(None, speed)
    assert event is None
    lean, _lean_old, _hip_x = pt.horizontal_signals(leaned, base)
    assert pt.hysteresis(None, lean, *pt.LEAN, "STEP_L", "STEP_R") == "STEP_L"


def test_leftward_hip_motion_is_one_step_then_ready_for_another():
    base = feat(0.50, 0.50)
    window = pt.STEP_WINDOW
    history = collections.deque()
    start = feat(0.50, 0.50, dx=0.20)
    moved = feat(0.50, 0.50, dx=0.10)
    pt.track_lateral_speed(history, start["hx"], 0.0, base["sw"])
    speed = pt.track_lateral_speed(history, moved["hx"], window, base["sw"])
    assert speed == -0.5 / window
    state, event = drive(None, speed)
    assert event == "STEP_LEFT"
    state, event = drive(state, speed)
    assert event is None
    state, event = settle(state)
    assert state is None
    state, event = drive(state, speed)
    assert event == "STEP_LEFT"


def test_left_step_then_stop_rearms_after_settle():
    state, event = drive(None, LEFT)
    assert event == "STEP_LEFT"
    state, event = drive(state, 0.0)
    assert event is None
    assert phase(state) == "RECOVER_LEFT"
    state, event = settle(state)
    assert event is None
    assert phase(state) == "NEUTRAL"


def test_left_step_snap_back_right_does_not_emit_step_right():
    state, event = drive(None, LEFT)
    assert event == "STEP_LEFT"
    state, event = drive(state, RIGHT, 0.30)
    assert event is None
    assert phase(state) == "RECOVER_LEFT"
    state, event = drive(state, RIGHT, 0.30)
    assert event is None
    assert phase(state) == "RECOVER_LEFT"


def test_left_step_stop_then_left_step_again():
    state, _event = drive(None, LEFT)
    state, _event = settle(state)
    assert phase(state) == "NEUTRAL"
    state, event = drive(state, LEFT)
    assert event == "STEP_LEFT"
    assert phase(state) == "MOVING_LEFT"


def test_left_step_settle_then_intentional_right_step():
    state, _event = drive(None, LEFT)
    state, _event = settle(state)
    state, event = drive(state, RIGHT)
    assert event == "STEP_RIGHT"
    assert phase(state) == "MOVING_RIGHT"


def test_right_step_snap_back_left_does_not_emit_step_left():
    state, event = drive(None, RIGHT)
    assert event == "STEP_RIGHT"
    state, event = drive(state, LEFT, 0.30)
    assert event is None
    assert phase(state) == "RECOVER_RIGHT"
    state, event = drive(state, LEFT, 0.30)
    assert event is None
    assert phase(state) == "RECOVER_RIGHT"


def test_small_lateral_jitter_does_not_emit():
    state, event = drive(None, 0.25, 0.50)
    assert event is None
    assert state is None
    state, _event = drive(None, LEFT)
    state, event = drive(state, -0.20)
    assert event is None
    assert phase(state) == "RECOVER_LEFT"
    state, event = drive(state, LEFT)
    assert event is None
    assert phase(state) == "MOVING_LEFT"


def test_continuous_left_movement_emits_once():
    state, event = drive(None, LEFT)
    assert event == "STEP_LEFT"
    for _ in range(30):
        state, event = drive(state, LEFT, 0.05)
        assert event is None
        assert phase(state) == "MOVING_LEFT"


def test_continuous_right_movement_emits_once():
    state, event = drive(None, RIGHT)
    assert event == "STEP_RIGHT"
    for _ in range(30):
        state, event = drive(state, RIGHT, 0.05)
        assert event is None
        assert phase(state) == "MOVING_RIGHT"


def test_brief_quiet_before_0_20s_does_not_rearm():
    state, _event = drive(None, LEFT)
    state, event = drive(state, 0.0, pt.STEP_WINDOW / 2)
    assert event is None
    assert phase(state) == "RECOVER_LEFT"
    state, event = drive(state, RIGHT)
    assert event is None
    assert phase(state) == "RECOVER_LEFT"
    state, event = drive(state, 0.0, pt.STEP_WINDOW / 2)
    assert event is None
    assert phase(state) == "RECOVER_LEFT"
    state, event = drive(state, LEFT)
    assert event is None
    assert phase(state) == "MOVING_LEFT"


def test_full_quiet_window_rearms():
    state, _event = drive(None, LEFT)
    state, event = drive(state, 0.0, pt.STEP_WINDOW / 2)
    assert phase(state) == "RECOVER_LEFT"
    state, event = drive(state, 0.0, pt.STEP_WINDOW / 2)
    assert event is None
    assert state is None
    assert phase(state) == "NEUTRAL"


SHIFT = 0.10  # calibration-scale hip travel, in normalized image x
EXPECTED = -SHIFT / SHOULDER_WIDTH / pt.STEP_WINDOW


def test_stationary_pose_has_about_zero_step_speed():
    base = pose_at_scale(0.0, 1.0)
    history = collections.deque()
    step_speeds(history, base, 0.0, base)
    live, old = step_speeds(history, pose_at_scale(0.0, 1.0), pt.STEP_WINDOW, base)
    assert abs(live) < 1e-9
    assert abs(old) < 1e-9


def test_leftward_movement_at_calibration_scale():
    base = pose_at_scale(0.0, 1.0)
    history = collections.deque()
    step_speeds(history, pose_at_scale(0.0, 1.0), 0.0, base)
    live, old = step_speeds(history, pose_at_scale(-SHIFT, 1.0), pt.STEP_WINDOW, base)
    assert abs(live - EXPECTED) < 1e-9
    assert abs(old - EXPECTED) < 1e-9
    assert live < 0


def test_equivalent_leftward_movement_at_smaller_scale_matches():
    base = pose_at_scale(0.0, 1.0)
    history = collections.deque()
    step_speeds(history, pose_at_scale(0.0, 0.5), 0.0, base)
    live, old = step_speeds(history, pose_at_scale(-SHIFT, 0.5), pt.STEP_WINDOW, base)
    assert abs(live - EXPECTED) < 1e-9
    assert abs(old - 0.5 * EXPECTED) < 1e-9
    assert abs(old) < abs(live)


def test_equivalent_leftward_movement_at_larger_scale_matches():
    base = pose_at_scale(0.0, 1.0)
    history = collections.deque()
    step_speeds(history, pose_at_scale(0.0, 1.8), 0.0, base)
    live, old = step_speeds(history, pose_at_scale(-SHIFT, 1.8), pt.STEP_WINDOW, base)
    assert abs(live - EXPECTED) < 1e-9
    assert abs(old - 1.8 * EXPECTED) < 1e-9
    assert abs(old) > abs(live)


def test_rightward_movement_matches_across_scales():
    base = pose_at_scale(0.0, 1.0)
    expected = -EXPECTED
    for scale in (1.0, 0.5, 1.8):
        history = collections.deque()
        step_speeds(history, pose_at_scale(0.0, scale), 0.0, base)
        live, old = step_speeds(history, pose_at_scale(SHIFT, scale), pt.STEP_WINDOW, base)
        assert abs(live - expected) < 1e-9
        assert live > 0
        assert abs(old - scale * expected) < 1e-9


def test_stationary_person_at_another_scale_emits_no_step():
    base = pose_at_scale(0.0, 1.0)
    parked = pose_at_scale(0.15, 0.55)
    history = collections.deque()
    step_speeds(history, parked, 0.0, base)
    live, _old = step_speeds(history, pose_at_scale(0.15, 0.55), pt.STEP_WINDOW, base)
    assert abs(live) < 1e-9
    state, event = drive(None, live)
    assert event is None
    assert state is None


def test_recovery_snap_back_still_swallows_the_opposite_speed():
    base = pose_at_scale(0.0, 1.0)
    history = collections.deque()
    step_speeds(history, pose_at_scale(0.0, 0.5), 0.0, base)
    left, _old = step_speeds(history, pose_at_scale(-SHIFT, 0.5), pt.STEP_WINDOW, base)
    state, event = drive(None, left)
    assert event == "STEP_LEFT"
    assert phase(state) == "MOVING_LEFT"
    state, event = drive(state, -left)
    assert event is None
    assert phase(state) == "RECOVER_LEFT"
