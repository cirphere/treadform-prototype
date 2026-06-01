"""
오버스트라이딩 지표.

착지 시점에서 발목 X 가 골반(hip) X 보다 얼마나 앞쪽에 있는지의 정규화 거리.
같은 발(좌/우)의 hip - ankle X 차이를 사용한다.

판정:
    distance > OVERSTRIDE_THRESHOLD → over_stride 🔴
    그 외 → good_stride 🟢   (PRD-2 §9 경계: 0.15 정확히 → good)
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from config import OVERSTRIDE_THRESHOLD

logger = logging.getLogger(__name__)


def calculate_overstride_distance(ankle: np.ndarray, hip: np.ndarray) -> float:
    """
    |ankle_x - hip_x| (정규화 좌표 절대값).
    """
    ankle = np.asarray(ankle, dtype=float)
    hip = np.asarray(hip, dtype=float)
    if np.any(np.isnan(ankle)) or np.any(np.isnan(hip)):
        return float("nan")
    return float(abs(ankle[0] - hip[0]))


def classify_overstride(distance: float) -> str:
    """
    Returns:
        "over_stride" | "good_stride"
    """
    if np.isnan(distance):
        return "good_stride"
    return "over_stride" if distance > OVERSTRIDE_THRESHOLD else "good_stride"


def analyze_overstriding(df: pd.DataFrame, strike_indices: dict) -> dict:
    """
    Returns:
        {
            "avg_distance": float,
            "status_counts": {"good": int, "over": int},
            "per_strike": [{"frame": int, "distance": float, "status": str, "foot": str}]
        }
    """
    per_strike: list[dict] = []
    counts = {"good": 0, "over": 0}
    distances: list[float] = []

    for side, frames in (("left", strike_indices["left"]), ("right", strike_indices["right"])):
        for f in frames:
            f = int(f)
            ankle = np.array(
                [df.at[f, f"{side}_ankle_x"], df.at[f, f"{side}_ankle_y"]], dtype=float
            )
            hip = np.array(
                [df.at[f, f"{side}_hip_x"], df.at[f, f"{side}_hip_y"]], dtype=float
            )
            dist = calculate_overstride_distance(ankle, hip)
            status = classify_overstride(dist)
            per_strike.append(
                {"frame": f, "distance": dist, "status": status, "foot": side}
            )
            if status == "over_stride":
                counts["over"] += 1
            else:
                counts["good"] += 1
            if not np.isnan(dist):
                distances.append(dist)

    result = {
        "avg_distance": float(np.mean(distances)) if distances else float("nan"),
        "status_counts": counts,
        "per_strike": sorted(per_strike, key=lambda x: x["frame"]),
    }
    logger.info(
        "overstride: avg=%.4f, counts=%s", result["avg_distance"], counts
    )
    return result


__all__ = [
    "calculate_overstride_distance",
    "classify_overstride",
    "analyze_overstriding",
]
