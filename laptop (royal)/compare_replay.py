"""Compare cached landmarks with a saved old detector and the live recognizer.

No webcam or output adapter is used. The recording's existing drawn skeleton may
affect inference, so this is a regression check rather than a raw-camera benchmark.
"""

import argparse
import collections
import csv
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pose_controller as current


def load_module(path):
    spec = importlib.util.spec_from_file_location("baseline_detector", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("cache", type=Path)
    parser.add_argument("baseline", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--calibration-start", type=float, default=9.0)
    parser.add_argument("--calibration-end", type=float, default=10.0)
    args = parser.parse_args()
    old = load_module(args.baseline)
    frames = []
    with args.cache.open(encoding="utf-8") as source:
        for line in source:
            row = json.loads(line)
            row["lm"] = [
                SimpleNamespace(x=p[0], y=p[1], visibility=p[2])
                for p in row.pop("landmarks")
            ]
            frames.append(row)
    calibration = [
        r
        for r in frames
        if args.calibration_start <= r["t"] < args.calibration_end
        and r["lm"]
        and min(current._visibility(r["lm"][i]) for i in (11, 12, 23, 24)) >= 0.5
    ]
    if not calibration:
        parser.error("No valid calibration frames in selected interval")
    base = current.average_baseline(
        [current.features(r["lm"], r["aspect"]) for r in calibration]
    )
    legs = [r for r in calibration if current.feet_observed(r["lm"])]
    base["leg"] = (
        sum(current.leg_ratio(r["lm"], base["sw"]) for r in legs) / len(legs)
        if legs
        else None
    )
    base["ay"] = (
        sum((r["lm"][27].y + r["lm"][28].y) / 2 for r in legs) / len(legs)
        if legs
        else None
    )
    recognizer = current.MotionRecognizer(base)
    history = collections.deque()
    lean, duck, step, last_t, prev = None, False, None, None, None
    last_hop = -100.0
    events = {"baseline": [], "revised": []}
    args.output.mkdir(parents=True, exist_ok=True)
    with (args.output / "signals.csv").open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=[
                "t",
                "hx",
                "sx",
                "hy",
                "sy",
                "sw",
                "hop_v",
                "rise",
                "step_v",
                "travel",
                "duck",
                "foot_up",
                "jump_phase",
                "reason",
            ],
        )
        writer.writeheader()
        for row in frames:
            t, lm, aspect = row["t"], row["lm"], row["aspect"]
            if t < args.calibration_end:
                continue
            valid = (
                lm and min(current._visibility(lm[i]) for i in (11, 12, 23, 24)) >= 0.5
            )
            output = recognizer.update(lm if valid else None, t, aspect)
            for event in output["events"]:
                events["revised"].append({"t": round(t, 3), "event": event})
            if not valid:
                history.clear()
                step, last_t, prev = None, None, None
                continue
            f = old.features(lm, aspect)
            writer.writerow(
                {
                    "t": round(t, 3),
                    **{k: f[k] for k in ("hx", "sx", "hy", "sy", "sw")},
                    **recognizer.values,
                    "jump_phase": recognizer.jump_phase,
                    "reason": recognizer.reason,
                }
            )
            found = []
            val, _, _ = old.horizontal_signals(f, base)
            new_lean = old.hysteresis(lean, val, *old.LEAN, "STEP_L", "STEP_R")
            if new_lean and new_lean != lean:
                found.append(new_lean)
            lean = new_lean
            speed = (
                0.0
                if prev is None
                else (prev[0] - f["hy"]) / (t - prev[1]) / base["torso"]
            )
            prev = (f["hy"], t)
            rise = (base["hy"] - f["hy"]) / base["torso"]
            if (
                speed > old.HOP_V
                and rise > old.HOP_RISE
                and t - last_hop > old.COOLDOWN
            ):
                found.append("HOP")
                last_hop = t
            value = old.crouch_measurement(lm, f["sw"], base["leg"])
            if t - last_hop > old.COOLDOWN and value is not None:
                duck, event = old.crouch_update(duck, value)
                if event:
                    found.append(event)
            speed = old.track_lateral_speed(history, f["hx"], t, f["sw"])
            step, event = old.step_update(
                step, speed, 0 if last_t is None else t - last_t
            )
            last_t = t
            if event:
                found.append(event)
            events["baseline"].extend({"t": round(t, 3), "event": e} for e in found)
    (args.output / "events.json").write_text(
        json.dumps({"calibration": base, **events}, indent=2), encoding="utf-8"
    )
    for method, result in events.items():
        print(method, collections.Counter(e["event"] for e in result))


if __name__ == "__main__":
    main()
