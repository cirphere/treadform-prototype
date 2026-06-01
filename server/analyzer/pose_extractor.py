"""
MediaPipe Pose 로 영상에서 33 keypoints × N frames 시계열을 추출.

PRD-0 절대 준수 제약:
    - 모델: MediaPipe Pose (BlazePose) 고정
    - model_complexity=2 (Heavy) 고정 → Tasks API 의 `pose_landmarker_heavy.task` 사용
    - PoseLandmark enum 으로만 접근 (숫자 인덱스 금지)

mediapipe 0.10.35 부터 legacy `mediapipe.solutions` API 가 제거되어
신규 Tasks API (`mediapipe.tasks.python.vision.PoseLandmarker`)를 사용한다.
heavy 모델 파일(.task)이 로컬에 없으면 자동 다운로드한다.
"""
from __future__ import annotations

import logging
import urllib.request
from enum import IntEnum
from pathlib import Path

import cv2
import mediapipe as mp
import numpy as np
import pandas as pd
from mediapipe.tasks.python import BaseOptions
from mediapipe.tasks.python.vision import (
    PoseLandmarker,
    PoseLandmarkerOptions,
    RunningMode,
)

from config import (
    MEDIAPIPE_MIN_DETECTION_CONFIDENCE,
    MEDIAPIPE_MIN_TRACKING_CONFIDENCE,
    MEDIAPIPE_MODEL_COMPLEXITY,
    TARGET_FPS,
)

logger = logging.getLogger(__name__)


# Tasks API 모델 파일 매핑.
# PRD-0 절대 준수: MEDIAPIPE_MODEL_COMPLEXITY == 2 → heavy.
_MODEL_URLS = {
    0: "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/latest/pose_landmarker_lite.task",
    1: "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_full/float16/latest/pose_landmarker_full.task",
    2: "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_heavy/float16/latest/pose_landmarker_heavy.task",
}


class PoseLandmark(IntEnum):
    """
    BlazePose 33 keypoints.

    legacy `mp.solutions.pose.PoseLandmark` 와 동일한 인덱스/네이밍을 유지해
    설정/문서/렌더링 코드가 그대로 동작하도록 한다.
    """

    NOSE = 0
    LEFT_EYE_INNER = 1
    LEFT_EYE = 2
    LEFT_EYE_OUTER = 3
    RIGHT_EYE_INNER = 4
    RIGHT_EYE = 5
    RIGHT_EYE_OUTER = 6
    LEFT_EAR = 7
    RIGHT_EAR = 8
    MOUTH_LEFT = 9
    MOUTH_RIGHT = 10
    LEFT_SHOULDER = 11
    RIGHT_SHOULDER = 12
    LEFT_ELBOW = 13
    RIGHT_ELBOW = 14
    LEFT_WRIST = 15
    RIGHT_WRIST = 16
    LEFT_PINKY = 17
    RIGHT_PINKY = 18
    LEFT_INDEX = 19
    RIGHT_INDEX = 20
    LEFT_THUMB = 21
    RIGHT_THUMB = 22
    LEFT_HIP = 23
    RIGHT_HIP = 24
    LEFT_KNEE = 25
    RIGHT_KNEE = 26
    LEFT_ANKLE = 27
    RIGHT_ANKLE = 28
    LEFT_HEEL = 29
    RIGHT_HEEL = 30
    LEFT_FOOT_INDEX = 31
    RIGHT_FOOT_INDEX = 32


def _model_path() -> Path:
    """
    heavy 모델 파일 경로. 없으면 다운로드.
    """
    complexity = MEDIAPIPE_MODEL_COMPLEXITY
    if complexity not in _MODEL_URLS:
        raise ValueError(f"unsupported MEDIAPIPE_MODEL_COMPLEXITY: {complexity}")

    cache_dir = Path(__file__).resolve().parent.parent / ".models"
    cache_dir.mkdir(exist_ok=True)
    name = Path(_MODEL_URLS[complexity]).name
    path = cache_dir / name

    if not path.exists():
        logger.info("downloading mediapipe model: %s", name)
        urllib.request.urlretrieve(_MODEL_URLS[complexity], path)
        logger.info("model saved: %s (%d bytes)", path, path.stat().st_size)
    return path


def _landmark_columns() -> list[str]:
    cols: list[str] = []
    for lm in PoseLandmark:
        name = lm.name.lower()
        cols.extend([f"{name}_x", f"{name}_y", f"{name}_z", f"{name}_visibility"])
    return cols


def extract_pose_series(video_path: str) -> pd.DataFrame:
    """
    영상 파일에서 33 keypoints × N frames 의 시계열 DataFrame 을 추출.

    Args:
        video_path: 분석할 영상(mp4) 경로.

    Returns:
        DataFrame.
            컬럼: frame_idx, timestamp_sec,
                  {landmark}_x, {landmark}_y, {landmark}_z, {landmark}_visibility (33개)
            attrs: {"fps": float, "frame_count": int, "video_path": str}

    Raises:
        FileNotFoundError: 영상 파일이 존재하지 않을 때.
        RuntimeError: cv2 가 영상을 열 수 없을 때.
    """
    path = Path(video_path)
    if not path.exists():
        raise FileNotFoundError(f"video not found: {video_path}")

    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise RuntimeError(f"cv2 cannot open video: {video_path}")

    fps = cap.get(cv2.CAP_PROP_FPS) or TARGET_FPS
    landmark_cols = _landmark_columns()

    options = PoseLandmarkerOptions(
        base_options=BaseOptions(model_asset_path=str(_model_path())),
        running_mode=RunningMode.VIDEO,
        num_poses=1,
        min_pose_detection_confidence=MEDIAPIPE_MIN_DETECTION_CONFIDENCE,
        min_pose_presence_confidence=MEDIAPIPE_MIN_DETECTION_CONFIDENCE,
        min_tracking_confidence=MEDIAPIPE_MIN_TRACKING_CONFIDENCE,
        output_segmentation_masks=False,
    )

    rows: list[dict] = []
    with PoseLandmarker.create_from_options(options) as landmarker:
        frame_idx = 0
        while True:
            ok, frame_bgr = cap.read()
            if not ok:
                break

            frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=frame_rgb)
            timestamp_ms = int(round(frame_idx * 1000.0 / fps))
            result = landmarker.detect_for_video(mp_image, timestamp_ms)

            row: dict = {
                "frame_idx": frame_idx,
                "timestamp_sec": frame_idx / fps,
            }

            # Tasks API 는 다중 pose 를 지원하지만 num_poses=1 이므로 첫 번째만 사용.
            landmarks_list = result.pose_landmarks  # list[list[NormalizedLandmark]]
            if not landmarks_list:
                for col in landmark_cols:
                    row[col] = float("nan")
            else:
                landmarks = landmarks_list[0]
                # visibility 무관하게 raw 좌표를 그대로 저장한다.
                # 가시화 시 모든 점을 활용 가능하고, 분석용 마스킹은
                # preprocess_pose_dataframe 에서 일괄 수행한다 (책임 분리).
                for lm in PoseLandmark:
                    pt = landmarks[lm.value]
                    vis = float(getattr(pt, "visibility", 1.0) or 0.0)
                    name = lm.name.lower()
                    row[f"{name}_x"] = pt.x
                    row[f"{name}_y"] = pt.y
                    row[f"{name}_z"] = pt.z
                    row[f"{name}_visibility"] = vis

            rows.append(row)
            frame_idx += 1

    cap.release()

    df = pd.DataFrame(rows)
    df.attrs["fps"] = float(fps)
    df.attrs["frame_count"] = int(len(df))
    df.attrs["video_path"] = str(path)

    logger.info(
        "pose extracted: frames=%d, fps=%.2f, video=%s",
        len(df),
        fps,
        path.name,
    )
    return df


# BlazePose 33 landmarks 의 표준 연결선.
# mediapipe v0.10.35 부터 `mp.solutions.pose.POSE_CONNECTIONS` 가 제거되어
# renderer/debug_overlay 가 공유할 수 있도록 여기에 정의한다.
# 인덱스는 legacy `mediapipe.solutions.pose.POSE_CONNECTIONS` 와 동일.
POSE_CONNECTIONS: tuple[tuple[PoseLandmark, PoseLandmark], ...] = (
    # 몸통
    (PoseLandmark.LEFT_SHOULDER, PoseLandmark.RIGHT_SHOULDER),
    (PoseLandmark.LEFT_SHOULDER, PoseLandmark.LEFT_HIP),
    (PoseLandmark.RIGHT_SHOULDER, PoseLandmark.RIGHT_HIP),
    (PoseLandmark.LEFT_HIP, PoseLandmark.RIGHT_HIP),
    # 왼팔
    (PoseLandmark.LEFT_SHOULDER, PoseLandmark.LEFT_ELBOW),
    (PoseLandmark.LEFT_ELBOW, PoseLandmark.LEFT_WRIST),
    # 오른팔
    (PoseLandmark.RIGHT_SHOULDER, PoseLandmark.RIGHT_ELBOW),
    (PoseLandmark.RIGHT_ELBOW, PoseLandmark.RIGHT_WRIST),
    # 왼다리
    (PoseLandmark.LEFT_HIP, PoseLandmark.LEFT_KNEE),
    (PoseLandmark.LEFT_KNEE, PoseLandmark.LEFT_ANKLE),
    (PoseLandmark.LEFT_ANKLE, PoseLandmark.LEFT_HEEL),
    (PoseLandmark.LEFT_HEEL, PoseLandmark.LEFT_FOOT_INDEX),
    (PoseLandmark.LEFT_ANKLE, PoseLandmark.LEFT_FOOT_INDEX),
    # 오른다리
    (PoseLandmark.RIGHT_HIP, PoseLandmark.RIGHT_KNEE),
    (PoseLandmark.RIGHT_KNEE, PoseLandmark.RIGHT_ANKLE),
    (PoseLandmark.RIGHT_ANKLE, PoseLandmark.RIGHT_HEEL),
    (PoseLandmark.RIGHT_HEEL, PoseLandmark.RIGHT_FOOT_INDEX),
    (PoseLandmark.RIGHT_ANKLE, PoseLandmark.RIGHT_FOOT_INDEX),
)


__all__ = ["extract_pose_series", "PoseLandmark", "POSE_CONNECTIONS"]
