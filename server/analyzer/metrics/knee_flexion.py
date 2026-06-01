"""
무릎 굴곡 각도 지표.

hip - knee - ankle 의 벡터 내적으로 무릎 안쪽 각도(°)를 산출.
4단계 판정: stiff_knee / borderline / good_flexion / over_bent.

흔한 함정 (PRD-2 #1): borderline 우선 판정.
임계값 ±KNEE_BORDERLINE_TOLERANCE 이내면 다른 판정보다 먼저 borderline 으로 처리.
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from config import (
    KNEE_BORDERLINE_TOLERANCE,
    KNEE_GOOD_MAX,
    KNEE_GOOD_MIN,
    KNEE_OVERBENT_THRESHOLD,
    KNEE_STIFF_THRESHOLD,
)

logger = logging.getLogger(__name__)


def calculate_knee_angle(
    hip: np.ndarray, knee: np.ndarray, ankle: np.ndarray
) -> float:
    """
    벡터 (hip→knee) 와 (ankle→knee) 의 내적각(°)을 계산.

    Returns:
        0 ~ 180. 좌표 중 NaN 이 있거나 영벡터인 경우 NaN.
    """
    hip = np.asarray(hip, dtype=float)
    knee = np.asarray(knee, dtype=float)
    ankle = np.asarray(ankle, dtype=float)

    if np.any(np.isnan(hip)) or np.any(np.isnan(knee)) or np.any(np.isnan(ankle)):
        return float("nan")

    v1 = hip - knee
    v2 = ankle - knee
    n1 = np.linalg.norm(v1)
    n2 = np.linalg.norm(v2)
    if n1 == 0.0 or n2 == 0.0:
        return float("nan")
    cos = float(np.dot(v1, v2) / (n1 * n2))
    cos = max(-1.0, min(1.0, cos))
    return float(np.degrees(np.arccos(cos)))


def classify_knee_status(angle: float) -> str:
    """
    Borderline 우선 판정 후 절대 비교.

    Returns:
        "stiff_knee" | "borderline" | "good_flexion" | "over_bent"
    """
    if np.isnan(angle):
        return "borderline"  # 결측은 보수적으로 경고 처리.

    # Borderline: 두 임계값 중 어느 쪽에라도 ±tol 안이면.
    if abs(angle - KNEE_STIFF_THRESHOLD) <= KNEE_BORDERLINE_TOLERANCE:
        return "borderline"
    if abs(angle - KNEE_OVERBENT_THRESHOLD) <= KNEE_BORDERLINE_TOLERANCE:
        return "borderline"

    if angle >= KNEE_STIFF_THRESHOLD:
        return "stiff_knee"
    if angle < KNEE_OVERBENT_THRESHOLD:
        return "over_bent"
    if KNEE_GOOD_MIN <= angle <= KNEE_GOOD_MAX:
        return "good_flexion"
    # KNEE_GOOD_MIN ~ KNEE_GOOD_MAX 사이가 아니지만 borderline/stiff/overbent 도 아닐 일은
    # 임계값이 같으면 발생하지 않는다. 안전망으로 borderline 반환.
    return "borderline"


def _xy(df: pd.DataFrame, side: str, joint: str, frame: int) -> np.ndarray:
    """단일 프레임에서 {side}_{joint}_x/y 를 (x,y) 로 추출."""
    return np.array(
        [df.at[frame, f"{side}_{joint}_x"], df.at[frame, f"{side}_{joint}_y"]],
        dtype=float,
    )


def analyze_knee_flexion(df: pd.DataFrame, strike_indices: dict) -> dict:
    """
    좌/우 착지 프레임에서 무릎 각도를 계산하고 상태별 집계.

    Returns:
        {
            "avg_angle": float,
            "left_avg": float,
            "right_avg": float,
            "status_counts": {"stiff": int, "good": int, "over_bent": int, "borderline": int},
            "per_strike": [{"frame": int, "angle": float, "status": str, "foot": str}]
        }
    """
    per_strike: list[dict] = []
    left_angles: list[float] = []
    right_angles: list[float] = []

    for side, frames in (("left", strike_indices["left"]), ("right", strike_indices["right"])):
        for f in frames:
            f = int(f)
            hip = _xy(df, side, "hip", f)
            knee = _xy(df, side, "knee", f)
            ankle = _xy(df, side, "ankle", f)
            angle = calculate_knee_angle(hip, knee, ankle)
            status = classify_knee_status(angle)
            per_strike.append(
                {"frame": f, "angle": angle, "status": status, "foot": side}
            )
            if not np.isnan(angle):
                (left_angles if side == "left" else right_angles).append(angle)

    counts = {"stiff": 0, "good": 0, "over_bent": 0, "borderline": 0}
    for entry in per_strike:
        s = entry["status"]
        if s == "stiff_knee":
            counts["stiff"] += 1
        elif s == "good_flexion":
            counts["good"] += 1
        elif s == "over_bent":
            counts["over_bent"] += 1
        else:
            counts["borderline"] += 1

    def _avg(xs: list[float]) -> float:
        return float(np.mean(xs)) if xs else float("nan")

    all_angles = left_angles + right_angles
    result = {
        "avg_angle": _avg(all_angles),
        "left_avg": _avg(left_angles),
        "right_avg": _avg(right_angles),
        "status_counts": counts,
        "per_strike": sorted(per_strike, key=lambda x: x["frame"]),
    }
    logger.info("knee flexion: avg=%.2f, counts=%s", result["avg_angle"], counts)
    return result


__all__ = ["calculate_knee_angle", "classify_knee_status", "analyze_knee_flexion"]
