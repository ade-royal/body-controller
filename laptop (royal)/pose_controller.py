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
EDGES = [(11, 12), (11, 13), (13, 15), (12, 14), (14, 16), (11, 23), (12, 24),
         (23, 24), (23, 25), (25, 27), (24, 26), (26, 28)]

# (enter, exit) thresholds -- tune these while watching the panel
STEP = (0.5, 0.3)    # hip shift, in shoulder-widths
DUCK = (0.25, 0.15)  # shoulder drop, in torso lengths
HOP_V = 1.5          # upward hip speed, torso lengths / second
HOP_RISE = 0.05      # hips must also be above neutral, so standing up from a duck isn't a hop
COOLDOWN = 0.4       # seconds after a hop where the landing can't trigger a duck

KEY = {"STEP_L": "LEFT", "STEP_R": "RIGHT", "HOP": "UP", "DUCK": "DOWN"}


def features(lm, aspect):
    # scale x by width/height so x and y are in the same units
    sx, sy = (lm[LSH].x + lm[RSH].x) / 2 * aspect, (lm[LSH].y + lm[RSH].y) / 2
    hx, hy = (lm[LHIP].x + lm[RHIP].x) / 2 * aspect, (lm[LHIP].y + lm[RHIP].y) / 2
    return {"sy": sy, "hx": hx, "hy": hy,
            "torso": math.hypot(sx - hx, sy - hy),            # body-size ruler
            "sw": abs(lm[LSH].x - lm[RSH].x) * aspect}        # body-size ruler


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


def main():
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

    base, samples, calib_end = None, [], 0.0
    step_s, duck_s = None, False
    prev, last_hop, last_ts = None, 0.0, -1
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

        status, vals = "no person", {}
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
                if now >= calib_end and samples:
                    base = {k: float(np.mean([s[k] for s in samples])) for k in f}
                    samples, calib_end = [], 0.0
            elif base:
                status = "tracking"
                vals["step"] = (f["hx"] - base["hx"]) / base["sw"]
                vals["duck"] = (f["sy"] - base["sy"]) / base["torso"]
                rise = (base["hy"] - f["hy"]) / base["torso"]
                vals["hop_v"] = 0.0 if prev is None else (prev[0] - f["hy"]) / (now - prev[1]) / base["torso"]
                prev = (f["hy"], now)

                events = []
                new = hysteresis(step_s, vals["step"], *STEP, "STEP_L", "STEP_R")
                if new and new != step_s:
                    events.append(new)
                step_s = new
                if vals["hop_v"] > HOP_V and rise > HOP_RISE and now - last_hop > COOLDOWN:
                    events.append("HOP")
                    last_hop = now
                if now - last_hop > COOLDOWN:
                    ducking = vals["duck"] > (DUCK[1] if duck_s else DUCK[0])
                    if ducking and not duck_s:
                        events.append("DUCK")
                    duck_s = ducking

                for e in events:
                    log.appendleft(f"{time.strftime('%H:%M:%S')}  {e:7} -> {KEY[e]}")
                    big, big_t = KEY[e], now
        else:
            prev = None

        panel = np.zeros((h, 380, 3), np.uint8)

        def put(text, y, color=(230, 230, 230), scale=0.55, thick=1):
            cv2.putText(panel, text, (12, y), cv2.FONT_HERSHEY_SIMPLEX, scale, color, thick)

        put(f"FPS {fps:4.0f}   pose {infer_ms:4.1f} ms", 28)
        put(status, 54, (0, 200, 255))
        rows = [("step", "sw", STEP[0], step_s), ("duck", "torso", DUCK[0], duck_s),
                ("hop_v", "/s", HOP_V, now - last_hop < 0.3)]
        for i, (name, unit, thr, active) in enumerate(rows):
            if name in vals:
                put(f"{name:6}{vals[name]:+7.2f} {unit:5} (fires {thr})", 90 + i * 26,
                    (0, 255, 0) if active else (200, 200, 200))
        if now - big_t < 0.6:
            cv2.putText(panel, big, (12, 220), cv2.FONT_HERSHEY_SIMPLEX, 1.6, (0, 255, 255), 3)
        for i, line in enumerate(log):
            put(line, 270 + i * 20, scale=0.45)

        cv2.imshow("body-controller test", np.hstack([frame, panel]))
        k = cv2.waitKey(1) & 0xFF
        if k == ord("q"):
            break
        if k == ord("c"):
            calib_end, samples, base, prev = now + 3.0, [], None, None
            step_s, duck_s = None, False

    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
