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

MODEL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pose_landmarker_lite.task")
MODEL_URL = ("https://storage.googleapis.com/mediapipe-models/pose_landmarker/"
             "pose_landmarker_lite/float16/latest/pose_landmarker_lite.task")

LSH, RSH, LHIP, RHIP = 11, 12, 23, 24  # left/right shoulder, left/right hip
LANK, RANK = 27, 28  # left/right ankle
EDGES = [(11, 12), (11, 13), (13, 15), (12, 14), (14, 16), (11, 23), (12, 24),
         (23, 24), (23, 25), (25, 27), (24, 26), (26, 28)]

# (enter, exit) thresholds -- tune these while watching the panel
# lean: shoulder-mid x minus hip-mid x, relative to the calibrated stance,
# in calibrated shoulder-widths. 0.20 is a clear torso tilt. Exit is 60% of
# enter so a held lean survives small jitter and releases once the torso
# comes most of the way back.
LEAN = (0.20, 0.12)
# Lateral step speed in current shoulder-widths per second. Hip midpoint,
# not ankles: a frame is already dropped unless the hips are visible, and a
# laptop camera often crops the feet. Enter 1.0 is one shoulder-width per
# second, a clear sidestep rather than standing jitter. Exit 0.40 ends the
# step once that travel has mostly stopped, so another step can count.
# STEP_WINDOW is the recent hip motion included in the speed.
STEP_V = (1.0, 0.40)
STEP_WINDOW = 0.20
# Crouch is the fraction of the calibrated hip-to-ankle span that has collapsed.
# 0.20 is a clear squat, not a small knee bend. Exit 0.12 releases once the
# legs are most of the way straight again.
DUCK = (0.20, 0.12)
HOP_V = 1.5          # upward hip speed, torso lengths / second
HOP_RISE = 0.05      # hips must also be above neutral, so standing up from a duck isn't a hop
COOLDOWN = 0.4       # seconds after a hop where the landing can't trigger a duck

KEY = {"STEP_L": "LEFT", "STEP_R": "RIGHT", "HOP": "UP", "DUCK": "DOWN",
      "STEP_LEFT": "STEP_LEFT", "STEP_RIGHT": "STEP_RIGHT"}


def features(lm, aspect):
    # scale x by width/height so x and y are in the same units
    sx, sy = (lm[LSH].x + lm[RSH].x) / 2 * aspect, (lm[LSH].y + lm[RSH].y) / 2
    hx, hy = (lm[LHIP].x + lm[RHIP].x) / 2 * aspect, (lm[LHIP].y + lm[RHIP].y) / 2
    return {"sx": sx, "sy": sy, "hx": hx, "hy": hy,
            "torso": math.hypot(sx - hx, sy - hy),            # body-size ruler
            "sw": abs(lm[LSH].x - lm[RSH].x) * aspect}        # body-size ruler


def _visibility(point):
    return 1.0 if point.visibility is None else point.visibility


def legs_visible(lm, minimum=0.5):
    return min(_visibility(lm[i]) for i in (LHIP, RHIP, LANK, RANK)) >= minimum


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


def horizontal_signals(current, base):
    """Return (lean, lean_old, hip_x).

    lean is the scale-free torso ratio and drives LEFT/RIGHT.
    lean_old is the previous image-gap formula, for comparison only.
    """
    gap = current["sx"] - current["hx"]
    base_gap = base["sx"] - base["hx"]
    lean = gap / current["sw"] - base_gap / base["sw"]
    lean_old = (gap - base_gap) / base["sw"]
    hip_x = (current["hx"] - base["hx"]) / base["sw"]
    return lean, lean_old, hip_x


def lateral_speed(hx_then, hx_now, dt, shoulder_width):
    """Hip-midpoint speed in shoulder-widths per second. Left is negative."""
    if dt <= 0 or shoulder_width <= 0:
        return 0.0
    return (hx_now - hx_then) / dt / shoulder_width


def hip_window(history, hx, now):
    """Record hip x. Return (hx_then, dt) over the recent STEP_WINDOW."""
    if history and now - history[-1][0] > STEP_WINDOW * 2:
        history.clear()
    history.append((now, hx))
    cutoff = now - STEP_WINDOW
    while len(history) > 2 and history[1][0] <= cutoff:
        history.popleft()
    t0, x0 = history[0]
    return x0, now - t0


def track_lateral_speed(history, hx, now, shoulder_width):
    """Record hip x and return speed over the recent STEP_WINDOW."""
    x0, dt = hip_window(history, hx, now)
    return lateral_speed(x0, hx, dt, shoulder_width)


def step_update(state, speed, dt):
    """Return (state, event). state is None, or (phase, quiet seconds).

    A step emits once on the way out. Recovery swallows the return trip.
    NEUTRAL returns only after speed stays inside the exit band for STEP_WINDOW.
    """
    enter, exit_ = STEP_V
    phase, quiet = (None, 0.0) if state is None else state
    event = None
    if phase == "MOVING_LEFT" and speed >= -exit_:
        phase, quiet = "RECOVER_LEFT", 0.0
    elif phase == "MOVING_RIGHT" and speed <= exit_:
        phase, quiet = "RECOVER_RIGHT", 0.0

    if phase == "RECOVER_LEFT":
        if speed <= -enter:
            phase, quiet = "MOVING_LEFT", 0.0
        elif abs(speed) <= exit_:
            quiet += dt
            if quiet >= STEP_WINDOW:
                phase, quiet = None, 0.0
        else:
            quiet = 0.0
    elif phase == "RECOVER_RIGHT":
        if speed >= enter:
            phase, quiet = "MOVING_RIGHT", 0.0
        elif abs(speed) <= exit_:
            quiet += dt
            if quiet >= STEP_WINDOW:
                phase, quiet = None, 0.0
        else:
            quiet = 0.0
    elif phase is None:
        if speed <= -enter:
            phase, event = "MOVING_LEFT", "STEP_LEFT"
        elif speed >= enter:
            phase, event = "MOVING_RIGHT", "STEP_RIGHT"

    if phase is None:
        return None, event
    return (phase, quiet), event


def step_label(state):
    if state is None:
        return "NEUTRAL"
    return state[0]


def hysteresis(state, value, enter, exit_, neg, pos):
    if state == neg:
        return neg if value < -exit_ else None
    if state == pos:
        return pos if value > exit_ else None
    if value <= -enter:
        return neg
    if value >= enter:
        return pos
    return None


def gesture_frame(events, lean_held, crouch_held):
    """Return this frame's canonical gesture output. Does not send keys.

    ``events`` lists gestures that began on this frame. Names are
    ``STEP_L``, ``STEP_R``, ``HOP``, ``DUCK``, ``STEP_LEFT``, and
    ``STEP_RIGHT``.

    ``lean_held`` stays ``STEP_L`` or ``STEP_R`` for the whole lean, or
    None once the torso is back. ``crouch_held`` stays True for the whole
    crouch. ``HOP``, ``STEP_LEFT``, and ``STEP_RIGHT`` are one-shot entries
    in ``events`` only; a step's recovery is not a held key.
    """
    return {
        "events": events,
        "lean_held": lean_held,
        "crouch_held": crouch_held,
    }


def main(on_gesture_frame=None):
    """Run pose tracking, optionally delivering frames to a separate output adapter."""
    if not os.path.exists(MODEL):
        print("Downloading pose model...")
        urllib.request.urlretrieve(MODEL_URL, MODEL)
    landmarker = vision.PoseLandmarker.create_from_options(vision.PoseLandmarkerOptions(
        base_options=mp_python.BaseOptions(model_asset_path=MODEL),
        running_mode=vision.RunningMode.VIDEO, num_poses=1))

    cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))  # MJPG unlocks higher fps on most webcams
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    cap.set(cv2.CAP_PROP_FPS, 60)
    if not cap.isOpened():
        raise SystemExit("Could not open webcam 0")

    base, samples, leg_samples, calib_end = None, [], [], 0.0
    step_s, duck_s = None, False
    prev, last_hop, last_ts = None, 0.0, -1
    hip_hist = collections.deque()
    lat_s, lat_t = None, None
    step_fired, step_fired_t = "", 0.0
    log = collections.deque(maxlen=10)
    big, big_t = "", 0.0
    start = last_frame = time.perf_counter()
    fps = 0.0

    while True:
        ok, frame = cap.read()
        if not ok:
            break
        now = time.perf_counter()
        fps = 0.9 * fps + 0.1 / max(now - last_frame, 1e-6)
        last_frame = now
        frame = cv2.flip(frame, 1)  # mirror: your left = screen left
        h, w = frame.shape[:2]

        ts = max(int((now - start) * 1000), last_ts + 1)  # VIDEO mode needs increasing timestamps
        last_ts = ts
        t = time.perf_counter()
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        res = landmarker.detect_for_video(mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb), ts)
        infer_ms = (time.perf_counter() - t) * 1000

        status, vals, legs_note = "no person", {}, ""
        lm = res.pose_landmarks[0] if res.pose_landmarks else None
        if lm and min(1.0 if lm[i].visibility is None else lm[i].visibility
                      for i in (LSH, RSH, LHIP, RHIP)) < 0.5:
            status, lm = "step back: shoulders/hips not visible", None

        if lm:
            for a, b in EDGES:
                cv2.line(frame, (int(lm[a].x * w), int(lm[a].y * h)),
                         (int(lm[b].x * w), int(lm[b].y * h)), (0, 255, 0), 2)
            f = features(lm, w / h)
            status = "press C to calibrate"
            if calib_end:
                status = f"hold still... {calib_end - now:.1f}s"
                if now > calib_end - 1.0:  # average the last second
                    samples.append(f)
                    if legs_visible(lm):
                        ratio = leg_ratio(lm, f["sw"])
                        if ratio is not None:
                            leg_samples.append(ratio)
                if now >= calib_end and samples:
                    base = average_baseline(samples)
                    base["leg"] = float(np.mean(leg_samples)) if leg_samples else None
                    samples, leg_samples, calib_end = [], [], 0.0
            elif base:
                status = "tracking"
                vals["lean"], vals["lean_old"], vals["hip_x"] = horizontal_signals(f, base)
                vals["duck_old"] = (f["sy"] - base["sy"]) / base["torso"]
                duck = crouch_measurement(lm, f["sw"], base.get("leg"))
                if duck is None:
                    legs_note = "low"
                else:
                    vals["duck"] = duck
                    legs_note = "ok"
                rise = (base["hy"] - f["hy"]) / base["torso"]
                vals["hop_v"] = 0.0 if prev is None else (prev[0] - f["hy"]) / (now - prev[1]) / base["torso"]
                prev = (f["hy"], now)

                events = []
                new = hysteresis(step_s, vals["lean"], *LEAN, "STEP_L", "STEP_R")
                if new and new != step_s:
                    events.append(new)
                step_s = new
                if vals["hop_v"] > HOP_V and rise > HOP_RISE and now - last_hop > COOLDOWN:
                    events.append("HOP")
                    last_hop = now
                if now - last_hop > COOLDOWN and "duck" in vals:
                    duck_s, duck_event = crouch_update(duck_s, vals["duck"])
                    if duck_event:
                        events.append(duck_event)

                x0, win_dt = hip_window(hip_hist, f["hx"], now)
                vals["step_v"] = lateral_speed(x0, f["hx"], win_dt, f["sw"])
                vals["step_old"] = lateral_speed(x0, f["hx"], win_dt, base["sw"])
                dt = 0.0 if lat_t is None else max(0.0, now - lat_t)
                lat_t = now
                lat_s, step_event = step_update(lat_s, vals["step_v"], dt)
                if step_event:
                    events.append(step_event)
                    step_fired, step_fired_t = step_event, now

                output = gesture_frame(events, step_s, duck_s)
                if on_gesture_frame is not None:
                    on_gesture_frame(output)

                for e in events:
                    log.appendleft(f"{time.strftime('%H:%M:%S')}  {e:7} -> {KEY[e]}")
                    big, big_t = KEY[e], now
        else:
            prev = None
            hip_hist.clear()
            lat_s, lat_t = None, None

        panel = np.zeros((h, 380, 3), np.uint8)

        def put(text, y, color=(230, 230, 230), scale=0.55, thick=1):
            cv2.putText(panel, text, (12, y), cv2.FONT_HERSHEY_SIMPLEX, scale, color, thick)

        put(f"FPS {fps:4.0f}   pose {infer_ms:4.1f} ms", 28)
        put(status, 54, (0, 200, 255))
        rows = [("lean", "sw", f"{LEAN[0]:.2f}", step_s), ("lean_old", "sw", None, False),
                ("hip_x", "sw", None, False),
                ("duck", "leg", f"{DUCK[0]:.2f}", duck_s),
                ("duck_old", "torso", None, False),
                ("hop_v", "/s", HOP_V, now - last_hop < 0.3),
                ("step_v", "sw/s", f"{STEP_V[0]:.1f}", lat_s),
                ("step_old", "sw/s", None, False)]
        for i, (name, unit, thr, active) in enumerate(rows):
            if name not in vals:
                continue
            note = "old" if thr is None else f"fires {thr}"
            put(f"{name:6}{vals[name]:+7.2f} {unit:5} ({note})", 90 + i * 26,
                (0, 255, 0) if active else (200, 200, 200))
        if legs_note == "low":
            put("duck   legs low", 168, (0, 80, 255))
        fired = step_fired if now - step_fired_t < 0.6 else "---"
        phase = step_label(lat_s)
        if phase.startswith("MOVING"):
            step_color = (0, 255, 0)
        elif phase.startswith("RECOVER"):
            step_color = (0, 200, 255)
        else:
            step_color = (200, 200, 200)
        put(f"step   {phase}", 298, step_color)
        put(f"fired  {fired}", 324, (0, 255, 255) if fired != "---" else (200, 200, 200))
        if now - big_t < 0.6:
            cv2.putText(panel, big, (12, 358), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 255, 255), 3)
        for i, line in enumerate(log):
            put(line, 392 + i * 20, scale=0.45)

        cv2.imshow("body-controller test", np.hstack([frame, panel]))
        k = cv2.waitKey(1) & 0xFF
        if k == ord("q"):
            break
        if k == ord("c"):
            calib_end, samples, leg_samples, base, prev = now + 3.0, [], [], None, None
            step_s, duck_s = None, False
            hip_hist.clear()
            lat_s, lat_t = None, None
            step_fired, step_fired_t = "", 0.0

    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
