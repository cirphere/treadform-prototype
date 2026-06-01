"""
수직 진폭 (Vertical Oscillation) 지표.

1 Stride (동일 발 연속 착지) 동안 골반 Y 의 (max - min).
좌/우 각각 hip Y 시리즈에 대해 같은 발 착지 인덱스 쌍 사이 진폭을 계산하고 평균.

흔한 함정 (PRD-2 #3): step (좌우 교차)이 아니라 stride (동일 발) 단위.
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from config import VERTICAL_OSC_HIGH_THRESHOLD

logger = logging.getLogger(__name__)


def calculate_oscillation_per_stride(
    hip_y_series: np.ndarray, same_foot_strikes: np.ndarray
) -> list[dict]:
    """
    Args:
        hip_y_series: 골반 Y 시계열 (좌 또는 우).
        same_foot_strikes: 동일 발의 착지 프레임 인덱스 (오름차순).

    Returns:
        [{"start_frame": int, "end_frame": int, "value": float}] (NaN 구간은 제외)
    """
    arr = np.asarray(hip_y_series, dtype=float)
    strides: list[dict] = []
    for i in range(len(same_foot_strikes) - 1):
        s = int(same_foot_strikes[i])
        e = int(same_foot_strikes[i + 1])
        if e <= s:
            continue
        segment = arr[s : e + 1]
        if segment.size == 0 or np.all(np.isnan(segment)):
            continue
        value = float(np.nanmax(segment) - np.nanmin(segment))
        strides.append({"start_frame": s, "end_frame": e, "value": value})
    return strides


def classify_oscillation(value: float) -> str:
    """
    Returns:
        "high_oscillation" | "good_oscillation"
    """
    if np.isnan(value):
        return "good_oscillation"
    return (
        "high_oscillation"
        if value > VERTICAL_OSC_HIGH_THRESHOLD
        else "good_oscillation"
    )


def analyze_vertical_oscillation(df: pd.DataFrame, strike_indices: dict) -> dict:
    """
    좌/우 각각 1 stride 단위로 진폭 계산 후 평균.

    Returns:
        {
            "avg_value": float,
            "left_avg": float,
            "right_avg": float,
            "status": "high" | "good",
            "per_stride": [{"start_frame", "end_frame", "value", "status", "foot"}]
        }
    """
    per_stride: list[dict] = []

    left_vals: list[float] = []
    for s in calculate_oscillation_per_stride(
        df["left_hip_y"].to_numpy(dtype=float), strike_indices["left"]
    ):
        status = classify_oscillation(s["value"])
        per_stride.append({**s, "status": status, "foot": "left"})
        left_vals.append(s["value"])

    right_vals: list[float] = []
    for s in calculate_oscillation_per_stride(
        df["right_hip_y"].to_numpy(dtype=float), strike_indices["right"]
    ):
        status = classify_oscillation(s["value"])
        per_stride.append({**s, "status": status, "foot": "right"})
        right_vals.append(s["value"])

    def _avg(xs: list[float]) -> float:
        return float(np.mean(xs)) if xs else float("nan")

    avg_value = _avg(left_vals + right_vals)
    overall_status = (
        "high"
        if (not np.isnan(avg_value) and avg_value > VERTICAL_OSC_HIGH_THRESHOLD)
        else "good"
    )

    result = {
        "avg_value": avg_value,
        "left_avg": _avg(left_vals),
        "right_avg": _avg(right_vals),
        "status": overall_status,
        "per_stride": sorted(per_stride, key=lambda x: x["start_frame"]),
    }
    logger.info("vertical osc: avg=%.4f, status=%s", avg_value, overall_status)
    return result


__all__ = [
    "calculate_oscillation_per_stride",
    "classify_oscillation",
    "analyze_vertical_oscillation",
]
