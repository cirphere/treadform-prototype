"""
측면 러닝 영상 기반 추가 폼 지표.

단일 카메라 2D pose 의 한계를 고려해 절대 진단보다 코칭용 proxy 로 계산한다.
분석 항목:
    - landing_tibia: 착지 시 정강이 기울기
    - torso_posture: 몸통 기울기
    - arm_position: 팔꿈치 각도
    - head_position: 머리 전방 위치
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from config import (
    ARM_ELBOW_MAX_GOOD,
    ARM_ELBOW_MIN_GOOD,
    HEAD_FORWARD_RATIO_THRESHOLD,
    TIBIA_OVERREACH_THRESHOLD,
    TORSO_LEAN_HIGH_THRESHOLD,
    TORSO_LEAN_LOW_THRESHOLD,
)
from analyzer.metrics.knee_flexion import calculate_knee_angle

logger = logging.getLogger(__name__)


def _xy(df: pd.DataFrame, name: str, frame: int) -> np.ndarray:
    return np.array([df.at[frame, f"{name}_x"], df.at[frame, f"{name}_y"]], dtype=float)


def _side_xy(df: pd.DataFrame, side: str, joint: str, frame: int) -> np.ndarray:
    return _xy(df, f"{side}_{joint}", frame)


def _midpoint(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    if np.any(np.isnan(a)) and np.any(np.isnan(b)):
        return np.array([float("nan"), float("nan")])
    if np.any(np.isnan(a)):
        return b
    if np.any(np.isnan(b)):
        return a
    return (a + b) / 2.0


def _angle_from_vertical(a: np.ndarray, b: np.ndarray) -> float:
    """a→b 벡터가 화면 세로축에서 벗어난 절대 각도(°)."""
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    if np.any(np.isnan(a)) or np.any(np.isnan(b)):
        return float("nan")
    dx = b[0] - a[0]
    dy = b[1] - a[1]
    if dx == 0.0 and dy == 0.0:
        return float("nan")
    return float(np.degrees(np.arctan2(abs(dx), abs(dy))))


def _avg(values: list[float]) -> float:
    finite = [v for v in values if not np.isnan(v)]
    return float(np.mean(finite)) if finite else float("nan")


def classify_tibia(angle: float) -> str:
    if np.isnan(angle):
        return "unknown"
    if angle > TIBIA_OVERREACH_THRESHOLD:
        return "overreach_tibia"
    return "good_tibia"


def analyze_landing_tibia(df: pd.DataFrame, strike_indices: dict) -> dict:
    per_strike: list[dict] = []
    angles: list[float] = []

    for side, frames in (("left", strike_indices["left"]), ("right", strike_indices["right"])):
        for f in frames:
            f = int(f)
            ankle = _side_xy(df, side, "ankle", f)
            knee = _side_xy(df, side, "knee", f)
            angle = _angle_from_vertical(ankle, knee)
            status = classify_tibia(angle)
            per_strike.append({"frame": f, "angle": angle, "status": status, "foot": side})
            if not np.isnan(angle):
                angles.append(angle)

    counts = {"good": 0, "overreach": 0, "unknown": 0}
    for entry in per_strike:
        if entry["status"] == "overreach_tibia":
            counts["overreach"] += 1
        elif entry["status"] == "good_tibia":
            counts["good"] += 1
        else:
            counts["unknown"] += 1

    return {
        "avg_angle": _avg(angles),
        "status_counts": counts,
        "per_strike": sorted(per_strike, key=lambda x: x["frame"]),
    }


def classify_torso_lean(angle: float) -> str:
    if np.isnan(angle):
        return "unknown"
    if angle < TORSO_LEAN_LOW_THRESHOLD:
        return "too_upright"
    if angle > TORSO_LEAN_HIGH_THRESHOLD:
        return "excessive_lean"
    return "neutral_torso"


def analyze_torso_posture(df: pd.DataFrame) -> dict:
    angles: list[float] = []
    for i in range(len(df)):
        hip = _midpoint(_xy(df, "left_hip", i), _xy(df, "right_hip", i))
        shoulder = _midpoint(_xy(df, "left_shoulder", i), _xy(df, "right_shoulder", i))
        angles.append(_angle_from_vertical(hip, shoulder))

    avg_angle = _avg(angles)
    status = classify_torso_lean(avg_angle)
    return {
        "avg_angle": avg_angle,
        "status": status,
        "thresholds": {
            "low": TORSO_LEAN_LOW_THRESHOLD,
            "high": TORSO_LEAN_HIGH_THRESHOLD,
        },
    }


def classify_arm_angle(angle: float) -> str:
    if np.isnan(angle):
        return "unknown"
    if angle < ARM_ELBOW_MIN_GOOD:
        return "too_tight"
    if angle > ARM_ELBOW_MAX_GOOD:
        return "too_open"
    return "good_arm_swing"


def analyze_arm_position(df: pd.DataFrame) -> dict:
    per_side: dict[str, dict] = {}
    all_angles: list[float] = []

    for side in ("left", "right"):
        angles: list[float] = []
        for i in range(len(df)):
            shoulder = _side_xy(df, side, "shoulder", i)
            elbow = _side_xy(df, side, "elbow", i)
            wrist = _side_xy(df, side, "wrist", i)
            angle = calculate_knee_angle(shoulder, elbow, wrist)
            angles.append(angle)
            if not np.isnan(angle):
                all_angles.append(angle)
        avg_angle = _avg(angles)
        per_side[side] = {"avg_angle": avg_angle, "status": classify_arm_angle(avg_angle)}

    avg_angle = _avg(all_angles)
    status = classify_arm_angle(avg_angle)
    return {
        "avg_angle": avg_angle,
        "status": status,
        "left_avg": per_side["left"]["avg_angle"],
        "right_avg": per_side["right"]["avg_angle"],
        "per_side": per_side,
    }


def classify_head_position(ratio: float) -> str:
    if np.isnan(ratio):
        return "unknown"
    if ratio > HEAD_FORWARD_RATIO_THRESHOLD:
        return "forward_head"
    return "aligned_head"


def analyze_head_position(df: pd.DataFrame) -> dict:
    ratios: list[float] = []
    for i in range(len(df)):
        shoulder = _midpoint(_xy(df, "left_shoulder", i), _xy(df, "right_shoulder", i))
        hip = _midpoint(_xy(df, "left_hip", i), _xy(df, "right_hip", i))
        left_ear = _xy(df, "left_ear", i)
        right_ear = _xy(df, "right_ear", i)
        nose = _xy(df, "nose", i)
        ear_mid = _midpoint(left_ear, right_ear)
        head = _midpoint(ear_mid, nose)
        torso_len = float(np.linalg.norm(shoulder - hip))
        if torso_len == 0.0 or np.any(np.isnan(shoulder)) or np.any(np.isnan(head)):
            ratios.append(float("nan"))
        else:
            ratios.append(float(abs(head[0] - shoulder[0]) / torso_len))

    avg_ratio = _avg(ratios)
    return {
        "avg_ratio": avg_ratio,
        "status": classify_head_position(avg_ratio),
        "threshold": HEAD_FORWARD_RATIO_THRESHOLD,
    }


def analyze_posture_metrics(df: pd.DataFrame, strike_indices: dict) -> dict:
    result = {
        "landing_tibia": analyze_landing_tibia(df, strike_indices),
        "torso_posture": analyze_torso_posture(df),
        "arm_position": analyze_arm_position(df),
        "head_position": analyze_head_position(df),
    }
    logger.info(
        "posture metrics: tibia=%.2f torso=%.2f arm=%.2f head=%.3f",
        result["landing_tibia"]["avg_angle"],
        result["torso_posture"]["avg_angle"],
        result["arm_position"]["avg_angle"],
        result["head_position"]["avg_ratio"],
    )
    return result


__all__ = [
    "analyze_posture_metrics",
    "analyze_landing_tibia",
    "analyze_torso_posture",
    "analyze_arm_position",
    "analyze_head_position",
    "classify_tibia",
    "classify_torso_lean",
    "classify_arm_angle",
    "classify_head_position",
]
