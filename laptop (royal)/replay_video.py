"""Cache pose landmarks from a video for repeatable, headless gesture checks.

Input should contain only the camera image, already oriented like the live feed.
This never opens a camera, window, or game-output connection.
"""

import argparse
import json
from pathlib import Path

import cv2
import mediapipe as mp
from mediapipe.tasks import python as mp_python
from mediapipe.tasks.python import vision


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("video", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    model = Path(__file__).with_name("pose_landmarker_lite.task")
    if not model.is_file():
        parser.error(f"Missing pose model: {model}")
    cap = cv2.VideoCapture(str(args.video))
    if not cap.isOpened():
        parser.error(f"Cannot open video: {args.video}")
    fps = cap.get(cv2.CAP_PROP_FPS)
    if fps <= 0:
        cap.release()
        parser.error("Video has no usable frame rate")
    options = vision.PoseLandmarkerOptions(
        base_options=mp_python.BaseOptions(model_asset_path=str(model)),
        running_mode=vision.RunningMode.VIDEO,
        num_poses=1,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    try:
        with (
            vision.PoseLandmarker.create_from_options(options) as detector,
            args.output.open("w", encoding="utf-8") as out,
        ):
            index = 0
            while True:
                ok, frame = cap.read()
                if not ok:
                    break
                now = index / fps
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                result = detector.detect_for_video(
                    mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb),
                    round(now * 1000),
                )
                points = result.pose_landmarks[0] if result.pose_landmarks else []
                out.write(
                    json.dumps(
                        {
                            "t": now,
                            "aspect": frame.shape[1] / frame.shape[0],
                            "landmarks": [[p.x, p.y, p.visibility] for p in points],
                        }
                    )
                    + "\n"
                )
                index += 1
                if index % 600 == 0:
                    print(f"Cached {now:.0f}s", flush=True)
        print(f"Saved {index} frames to {args.output}")
    finally:
        cap.release()


if __name__ == "__main__":
    main()
