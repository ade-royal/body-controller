"""Body-controller pose test: shows which key each movement would press. No real input is sent.

Controls: C = calibrate (stand in your neutral stance, hold still 3s), Q = quit.
"""

import collections
import math
import os
import time
import urllib.request

import cv2
import mediapipe as mp
import numpy as np
from mediapipe.tasks import python as mp_python
from mediapipe.tasks.python import vision

MODEL = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "pose_landmarker_lite.task"
)
MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/pose_landmarker/"
    "pose_landmarker_lite/float16/latest/pose_landmarker_lite.task"
)

LSH, RSH, LHIP, RHIP = 11, 12, 23, 24  # left/right shoulder, left/right hip
LANK, RANK = 27, 28  # left/right ankle
EDGES = [
    (11, 12),
    (11, 13),
    (13, 15),
    (12, 14),
    (14, 16),
    (11, 23),
    (12, 24),
    (23, 24),
    (23, 25),
    (25, 27),
    (24, 26),
    (26, 28),
]

# Live recognizer settings. Distances are body-relative, times are seconds.
# Lean is disabled. A movement needs travel plus speed; a jump needs takeoff
# evidence and a completed landing before it can repeat.
DUCK = (0.20, 0.12)
TRAVEL_EXIT_SPEED = 0.40
MOTION_WINDOW = 0.12
TRACKING_GAP = 0.25
SMOOTH_SECONDS = 0.035
TRAVEL_MIN = 0.25  # shoulder widths from start / latest turning point
TRAVEL_SPEED = 1.0  # shoulder widths per second
TRAVEL_CONFIRM = 0.05
TRAVEL_SETTLE = 0.16
JUMP_SPEED = 0.70  # torso lengths per second over MOTION_WINDOW
JUMP_RISE = 0.10  # torso lengths above standing hips
FOOT_RISE = 0.045  # extra takeoff evidence when ankles are visible
CROUCH_CONFIRM = 0.06
LANDING_SETTLE = 0.06

KEY = {
    "STEP_L": "LEFT",
    "STEP_R": "RIGHT",
    "HOP": "UP",
    "DUCK": "DOWN",
    "STEP_LEFT": "STEP_LEFT",
    "STEP_RIGHT": "STEP_RIGHT",
}


def features(lm, aspect):
    # scale x by width/height so x and y are in the same units
    sx, sy = (lm[LSH].x + lm[RSH].x) / 2 * aspect, (lm[LSH].y + lm[RSH].y) / 2
    hx, hy = (lm[LHIP].x + lm[RHIP].x) / 2 * aspect, (lm[LHIP].y + lm[RHIP].y) / 2
    return {
        "sx": sx,
        "sy": sy,
        "hx": hx,
        "hy": hy,
        "torso": math.hypot(sx - hx, sy - hy),  # body-size ruler
        "sw": abs(lm[LSH].x - lm[RSH].x) * aspect,
    }  # body-size ruler


def _visibility(point):
    value = 1.0 if point.visibility is None else point.visibility
    return value if math.isfinite(value) else 0.0


def legs_visible(lm, minimum=0.5):
    return min(_visibility(lm[i]) for i in (LHIP, RHIP, LANK, RANK)) >= minimum


def feet_observed(lm):
    """Extrapolated ankles beyond the camera image are not takeoff evidence."""
    return legs_visible(lm) and all(
        math.isfinite(lm[i].x)
        and math.isfinite(lm[i].y)
        and 0 <= lm[i].x <= 1
        and 0 <= lm[i].y <= 1
        for i in (LANK, RANK)
    )


def leg_ratio(lm, shoulder_width):
    """Vertical hip-to-ankle span divided by current shoulder width."""
    if shoulder_width <= 0:
        return None
    hy = (lm[LHIP].y + lm[RHIP].y) / 2
    ay = (lm[LANK].y + lm[RANK].y) / 2
    return (ay - hy) / shoulder_width


def crouch_measurement(lm, shoulder_width, neutral):
    """Fraction of the calibrated leg span that has collapsed, or None."""
    if neutral is None or neutral <= 0 or not legs_visible(lm):
        return None
    ratio = leg_ratio(lm, shoulder_width)
    if ratio is None:
        return None
    return (neutral - ratio) / neutral


def crouch_update(holding, value):
    """Return (holding, event). One DUCK event when the crouch begins."""
    ducking = value > (DUCK[1] if holding else DUCK[0])
    event = "DUCK" if ducking and not holding else None
    return ducking, event


def average_baseline(samples):
    return {k: float(np.mean([s[k] for s in samples])) for k in samples[0]}


def gesture_frame(events, lean_held, crouch_held):
    """Return this frame's canonical gesture output. Does not send keys.

    ``events`` lists HOP, DUCK, STEP_LEFT and STEP_RIGHT when actions begin.
    Live recognition always supplies None for ``lean_held``; the field is kept
    for adapter compatibility. ``crouch_held`` stays True while crouching.
    Held output never repeats a one-shot event.
    """
    return {
        "events": events,
        "lean_held": lean_held,
        "crouch_held": crouch_held,
    }


class LateralMotion:
    """One event per travel action, including deliberate immediate reversals."""

    def __init__(self):
        self.history = collections.deque()
        self.anchor = None
        self.direction = 0
        self.quiet = 0.0
        self.candidate = 0
        self.confirm = 0.0
        self.speed = 0.0
        self.travel = 0.0
        self.reason = "waiting for travel"

    def update(self, hx: float, sx: float, now: float, width: float) -> str | None:
        center = (hx + sx) / 2
        if not self.history:
            self.anchor = (center, hx, sx)
            self.history.append((now, center))
            return None
        dt = now - self.history[-1][0]
        self.history.append((now, center))
        while len(self.history) > 2 and self.history[1][0] <= now - MOTION_WINDOW:
            self.history.popleft()
        elapsed = now - self.history[0][0]
        self.speed = (center - self.history[0][1]) / max(elapsed, 1e-6) / width
        if self.direction and self.direction * (center - self.anchor[0]) > 0:
            # Follow the furthest point reached, so reversal is measured locally.
            self.anchor = (center, hx, sx)
        delta = (center - self.anchor[0]) / width
        self.travel = delta
        direction = 1 if delta > 0 else -1
        evidence = (
            abs(delta) >= TRAVEL_MIN
            and direction * self.speed >= TRAVEL_SPEED
            and direction * (hx - self.anchor[1]) / width >= TRAVEL_MIN * 0.6
            and direction * (sx - self.anchor[2]) / width >= TRAVEL_MIN * 0.3
            and direction != self.direction
        )
        if evidence:
            self.confirm = self.confirm + dt if self.candidate == direction else dt
            self.candidate = direction
            self.reason = "confirming travel"
            if self.confirm >= TRAVEL_CONFIRM:
                self.direction = direction
                self.anchor = (center, hx, sx)
                self.candidate, self.confirm, self.quiet = 0, 0.0, 0.0
                self.reason = "travel accepted"
                return "STEP_RIGHT" if direction > 0 else "STEP_LEFT"
        else:
            self.candidate, self.confirm = 0, 0.0
            self.reason = (
                "waiting for travel" if not self.direction else "action active"
            )
        if abs(self.speed) < TRAVEL_EXIT_SPEED:
            self.quiet += dt
            if self.quiet >= TRAVEL_SETTLE:
                self.direction = 0
                self.anchor = (center, hx, sx)
                self.reason = "ready"
        else:
            self.quiet = 0.0
        return None

    @property
    def phase(self):
        return {0: "READY", -1: "MOVING_LEFT", 1: "MOVING_RIGHT"}[self.direction]


class MotionRecognizer:
    """Interpret landmark motion without knowing about games or sending inputs.

    Uses the existing event names for adapter compatibility. Lean output is always
    None. All motion history is discarded on tracking loss or a long frame gap.
    """

    def __init__(self, baseline):
        self.base = baseline.copy()
        self.width = max(baseline["sw"], 1e-4)
        self.torso = max(baseline["torso"], 1e-4)
        self.neutral_hy = baseline["hy"]
        self.neutral_sy = baseline["sy"]
        self.neutral_ay = baseline.get("ay")
        self.reset()

    def reset(self):
        self.history = collections.deque()
        self.lateral = LateralMotion()
        self.smoothed = None
        self.last_time = None
        self.crouch_held = False
        self.crouch_active = False
        self.crouch_seconds = 0.0
        self.crouch_release_seconds = 0.0
        self.recovering = False
        self.standing_seconds = 0.0
        self.jump_phase = "READY"
        self.landing_seconds = 0.0
        self.landed_at = -math.inf
        self.reason = "waiting for stable tracking"
        self.values = {}
        self.tracking_ready = False
        self.ready_seconds = 0.0

    def update(self, lm, now: float, aspect: float) -> dict:
        if lm is None or min(_visibility(lm[i]) for i in (LSH, RSH, LHIP, RHIP)) < 0.5:
            self.reset()
            return gesture_frame([], None, False)
        f = features(lm, aspect)
        if not all(math.isfinite(v) for v in f.values()) or f["torso"] < 0.02:
            self.reset()
            return gesture_frame([], None, False)
        if self.last_time is not None and (
            now <= self.last_time or now - self.last_time > TRACKING_GAP
        ):
            self.reset()
        dt = 0.0 if self.last_time is None else now - self.last_time
        self.last_time = now
        ay = (lm[LANK].y + lm[RANK].y) / 2 if feet_observed(lm) else None
        if ay is not None and not math.isfinite(ay):
            ay = None
        alpha = 1.0 if self.smoothed is None else 1 - math.exp(-dt / SMOOTH_SECONDS)
        old = self.smoothed or f
        f = {k: old[k] + alpha * (v - old[k]) for k, v in f.items()}
        self.smoothed = f
        self.history.append((now, f["hy"], f["sy"]))
        while len(self.history) > 2 and self.history[1][0] <= now - MOTION_WINDOW:
            self.history.popleft()
        elapsed = now - self.history[0][0]
        hv = (self.history[0][1] - f["hy"]) / max(elapsed, 1e-6) / self.torso
        sv = (self.history[0][2] - f["sy"]) / max(elapsed, 1e-6) / self.torso
        rise = (self.neutral_hy - f["hy"]) / self.torso
        shoulder_rise = (self.neutral_sy - f["sy"]) / self.torso
        foot_rise = (
            None
            if ay is None or self.neutral_ay is None
            else (self.neutral_ay - ay) / self.torso
        )
        neutral_leg = self.base.get("leg")
        duck = (
            None
            if ay is None or not neutral_leg
            else (1 - (ay - f["hy"]) / self.width / neutral_leg)
        )
        stable = abs(hv) < 0.20 and abs(sv) < 0.20
        grounded = (
            foot_rise <= FOOT_RISE * 0.5 if foot_rise is not None else abs(rise) <= 0.06
        )
        if not self.tracking_ready:
            if grounded and stable and abs(rise) < 0.12:
                self.ready_seconds += dt
                self.tracking_ready = self.ready_seconds >= MOTION_WINDOW
            else:
                self.ready_seconds = 0.0
        events = []
        takeoff = (
            self.tracking_ready
            and elapsed >= MOTION_WINDOW * 0.5
            and hv >= JUMP_SPEED
            and sv >= JUMP_SPEED * 0.5
            and rise >= JUMP_RISE
            and shoulder_rise >= JUMP_RISE * 0.6
        )
        if foot_rise is not None:
            takeoff = takeoff and foot_rise >= FOOT_RISE
        else:
            # With cropped feet, demand a larger coordinated rise. Recovery alone
            # cannot establish takeoff in this mode.
            takeoff = (
                takeoff
                and rise >= 0.22
                and shoulder_rise >= 0.16
                and not self.recovering
            )
        if self.jump_phase == "READY" and takeoff:
            events.append("HOP")
            self.jump_phase = "AIRBORNE"
            self.crouch_held, self.crouch_seconds = False, 0.0
            self.crouch_active = False
            self.crouch_release_seconds = 0.0
            self.reason = "takeoff accepted"
        elif self.jump_phase != "READY":
            if hv < -0.2:
                self.jump_phase = "LANDING"
            if self.jump_phase == "LANDING" and grounded:
                self.landing_seconds += dt
                if self.landing_seconds >= LANDING_SETTLE:
                    self.jump_phase = "READY"
                    self.landed_at = now
                    self.recovering = True
                    self.landing_seconds = 0.0
            else:
                self.landing_seconds = 0.0
            self.reason = "jump active; waiting for landing"
        else:
            self.reason = "waiting for coordinated takeoff"
            if self.recovering:
                self.reason = "crouch / landing recovery"
            elif foot_rise is not None and takeoff is False and hv >= JUMP_SPEED:
                self.reason = "rise without takeoff evidence"

        if (
            self.jump_phase == "READY"
            and self.tracking_ready
            and now - self.landed_at > 0.12
            and duck is not None
        ):
            if self.crouch_active:
                if duck <= DUCK[1]:
                    self.crouch_release_seconds += dt
                    if self.crouch_release_seconds >= CROUCH_CONFIRM:
                        self.crouch_held, self.crouch_active = False, False
                        self.crouch_seconds = 0.0
                else:
                    self.crouch_release_seconds = 0.0
                    self.crouch_held = True
                self.recovering = True
            elif duck > DUCK[0]:
                self.crouch_seconds += dt
                self.recovering = True
                if self.crouch_seconds >= CROUCH_CONFIRM:
                    self.crouch_held = True
                    self.crouch_active = True
                    self.crouch_release_seconds = 0.0
                    events.append("DUCK")
            else:
                self.crouch_seconds = 0.0
        elif duck is None:
            # Release unavailable held output, but retain recovery memory.
            self.crouch_held = False
            self.crouch_seconds = 0.0

        upright = duck is None or duck < DUCK[1]
        if self.jump_phase == "READY" and upright and stable and abs(rise) < 0.10:
            self.standing_seconds += dt
            if self.standing_seconds >= TRAVEL_SETTLE:
                self.recovering = False
                adjust = 1 - math.exp(-dt / 1.5)
                ratio = f["torso"] / self.torso
                if 0.75 < ratio < 1.25:
                    self.width *= 1 + adjust * (ratio - 1)
                    self.torso += adjust * (f["torso"] - self.torso)
                self.neutral_hy += adjust * (f["hy"] - self.neutral_hy)
                self.neutral_sy += adjust * (f["sy"] - self.neutral_sy)
                if ay is not None:
                    self.neutral_ay = (
                        ay
                        if self.neutral_ay is None
                        else (self.neutral_ay + adjust * (ay - self.neutral_ay))
                    )
        else:
            self.standing_seconds = 0.0

        lateral_event = self.lateral.update(f["hx"], f["sx"], now, self.width)
        if lateral_event:
            events.append(lateral_event)
        self.values = {
            "hop_v": hv,
            "rise": rise,
            "step_v": self.lateral.speed,
            "travel": self.lateral.travel,
        }
        if duck is not None:
            self.values["duck"] = duck
        if foot_rise is not None:
            self.values["foot_up"] = foot_rise
        return gesture_frame(events, None, self.crouch_held)


def main(on_gesture_frame=None):
    """Run pose tracking, optionally delivering frames to a separate output adapter."""
    if not os.path.exists(MODEL):
        print("Downloading pose model...")
        urllib.request.urlretrieve(MODEL_URL, MODEL)
    landmarker = vision.PoseLandmarker.create_from_options(
        vision.PoseLandmarkerOptions(
            base_options=mp_python.BaseOptions(model_asset_path=MODEL),
            running_mode=vision.RunningMode.VIDEO,
            num_poses=1,
        )
    )

    cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
    cap.set(
        cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG")
    )  # MJPG unlocks higher fps on most webcams
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    cap.set(cv2.CAP_PROP_FPS, 60)
    if not cap.isOpened():
        cap.release()
        landmarker.close()
        raise SystemExit("Could not open webcam 0")

    base, samples, leg_samples, calib_end = None, [], [], 0.0
    recognizer = None
    last_ts = -1
    step_fired, step_fired_t = "", 0.0
    log = collections.deque(maxlen=4)
    big, big_t = "", 0.0
    start = last_frame = time.perf_counter()
    fps = 0.0

    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            now = time.perf_counter()
            fps = 0.9 * fps + 0.1 / max(now - last_frame, 1e-6)
            last_frame = now
            frame = cv2.flip(frame, 1)  # mirror: your left = screen left
            h, w = frame.shape[:2]

            ts = max(
                int((now - start) * 1000), last_ts + 1
            )  # VIDEO mode needs increasing timestamps
            last_ts = ts
            t = time.perf_counter()
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            res = landmarker.detect_for_video(
                mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb), ts
            )
            infer_ms = (time.perf_counter() - t) * 1000

            status, vals, legs_note = "no person", {}, ""
            lm = res.pose_landmarks[0] if res.pose_landmarks else None
            if lm and min(_visibility(lm[i]) for i in (LSH, RSH, LHIP, RHIP)) < 0.5:
                status, lm = "step back: shoulders/hips not visible", None
            if lm and not all(math.isfinite(p.x) and math.isfinite(p.y) for p in lm):
                status, lm = "unstable pose tracking", None

            if lm:
                for a, b in EDGES:
                    cv2.line(
                        frame,
                        (int(lm[a].x * w), int(lm[a].y * h)),
                        (int(lm[b].x * w), int(lm[b].y * h)),
                        (0, 255, 0),
                        2,
                    )
                f = features(lm, w / h)
                status = "press C to calibrate"
                if calib_end:
                    status = f"hold still... {calib_end - now:.1f}s"
                    if now > calib_end - 1.0:  # average the last second
                        usable = (
                            all(math.isfinite(v) for v in f.values())
                            and f["torso"] >= 0.02
                            and f["sw"] >= 0.005
                        )
                        if usable:
                            samples.append(f)
                        if usable and feet_observed(lm):
                            ratio = leg_ratio(lm, f["sw"])
                            if ratio is not None:
                                leg_samples.append(
                                    (ratio, (lm[LANK].y + lm[RANK].y) / 2)
                                )
                    if now >= calib_end and samples:
                        base = average_baseline(samples)
                        base["leg"] = (
                            float(np.mean([s[0] for s in leg_samples]))
                            if leg_samples
                            else None
                        )
                        base["ay"] = (
                            float(np.mean([s[1] for s in leg_samples]))
                            if leg_samples
                            else None
                        )
                        recognizer = MotionRecognizer(base)
                        samples, leg_samples, calib_end = [], [], 0.0
                elif base:
                    status = "tracking"
                    output = recognizer.update(lm, now, w / h)
                    vals = recognizer.values
                    legs_note = "ok" if "duck" in vals else "low"
                    events = output["events"]
                    for event in events:
                        if event.startswith("STEP_"):
                            step_fired, step_fired_t = event, now
                    if on_gesture_frame is not None:
                        on_gesture_frame(output)

                    for e in events:
                        log.appendleft(
                            f"{time.strftime('%H:%M:%S')}  {e:7} -> {KEY[e]}"
                        )
                        big, big_t = KEY[e], now
            else:
                if recognizer is not None:
                    output = recognizer.update(None, now, w / h)
                    if on_gesture_frame is not None:
                        on_gesture_frame(output)

            panel = np.zeros((h, 380, 3), np.uint8)

            def put(text, y, color=(230, 230, 230), scale=0.55, thick=1, panel=panel):
                cv2.putText(
                    panel, text, (12, y), cv2.FONT_HERSHEY_SIMPLEX, scale, color, thick
                )

            put(f"FPS {fps:4.0f}   pose {infer_ms:4.1f} ms", 28)
            put(status, 54, (0, 200, 255))
            put("lean inputs disabled", 78, (0, 200, 255))
            rows = [
                ("travel", "sw", TRAVEL_MIN, False),
                ("step_v", "sw/s", TRAVEL_SPEED, False),
                ("duck", "leg", DUCK[0], recognizer and recognizer.crouch_held),
                ("hop_v", "/s", JUMP_SPEED, False),
                ("rise", "torso", JUMP_RISE, False),
                ("foot_up", "torso", FOOT_RISE, False),
            ]
            for i, (name, unit, thr, active) in enumerate(rows):
                if name not in vals:
                    continue
                note = f"needs {thr:.2f}"
                put(
                    f"{name:7}{vals[name]:+6.2f} {unit:5} ({note})",
                    106 + i * 24,
                    (0, 255, 0) if active else (200, 200, 200),
                )
            if legs_note == "low":
                put("legs hidden: limited jump evidence", 154, (0, 80, 255), scale=0.45)
            fired = step_fired if now - step_fired_t < 0.6 else "---"
            phase = recognizer.lateral.phase if recognizer else "UNCALIBRATED"
            if phase.startswith("MOVING"):
                step_color = (0, 255, 0)
            elif phase.startswith("RECOVER"):
                step_color = (0, 200, 255)
            else:
                step_color = (200, 200, 200)
            put(f"step   {phase}", 266, step_color)
            if recognizer:
                put(f"jump   {recognizer.jump_phase}", 288)
                put(recognizer.reason, 310, scale=0.43)
                put(recognizer.lateral.reason, 330, scale=0.43)
            put(
                f"fired  {fired}",
                350,
                (0, 255, 255) if fired != "---" else (200, 200, 200),
            )
            if now - big_t < 0.6:
                cv2.putText(
                    panel,
                    big,
                    (12, 385),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.9,
                    (0, 255, 255),
                    2,
                )
            for i, line in enumerate(log):
                put(line, 408 + i * 20, scale=0.45)

            cv2.imshow("body-controller test", np.hstack([frame, panel]))
            k = cv2.waitKey(1) & 0xFF
            if k == ord("q"):
                break
            if k == ord("c"):
                calib_end, samples, leg_samples, base = now + 3.0, [], [], None
                recognizer = None
                if on_gesture_frame is not None:
                    on_gesture_frame(gesture_frame([], None, False))
                step_fired, step_fired_t = "", 0.0

    finally:
        cap.release()
        landmarker.close()
        cv2.destroyAllWindows()
        if on_gesture_frame is not None:
            on_gesture_frame(gesture_frame([], None, False))


if __name__ == "__main__":
    main()
