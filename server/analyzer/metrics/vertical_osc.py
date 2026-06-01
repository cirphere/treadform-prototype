"""
수직 진폭 (Vertical Oscillation) 지표.

1 Stride (동일 발 연속 착지) 동안 골반 Y 의 (max - min).
좌/우 각각 hip Y 시리즈에 대해 같은 발 착지 인덱스 쌍 사이 진폭을 계산하고 평균.

흔한 함정 (PRD-2 #3): step (좌우 교차)이 아니라 stride (동일 발) 단위.

cm-aware 모드 (Phase 1, 2026-05-28):
    height_cm + body_norm_length 가 둘 다 주어지면 정규화 진폭을 cm 로 환산해
    VO_HIGH_THRESHOLD_CM (10cm, Cavanagh & Williams 1982) 임계로 판정.
    하나라도 None/NaN 이면 기존 VERTICAL_OSC_HIGH_THRESHOLD (0.06 정규화) fallback.
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from config import VERTICAL_OSC_HIGH_THRESHOLD, VO_HIGH_THRESHOLD_CM

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


def classify_oscillation(
    value: float,
    threshold: float = VERTICAL_OSC_HIGH_THRESHOLD,
) -> str:
    """
    Returns:
        "high_oscillation" | "good_oscillation"

    threshold 의 단위는 호출측 책임 (정규화면 norm 임계, cm 면 cm 임계).
    """
    if np.isnan(value):
        return "good_oscillation"
    return "high_oscillation" if value > threshold else "good_oscillation"


def _resolve_threshold_norm(
    height_cm: float | None, body_norm_length: float | None
) -> tuple[float, float | None, float | None]:
    """
    cm-aware 모드 가능 여부 판정 후 정규화 임계 + scale + cm 임계 반환.

    Returns:
        (threshold_norm, scale_cm_per_norm | None, threshold_cm | None)
        cm-aware 모드 OFF 면 scale/threshold_cm 가 None.
    """
    if (
        height_cm is None
        or body_norm_length is None
        or not np.isfinite(height_cm)
        or not np.isfinite(body_norm_length)
        or body_norm_length <= 0.0
        or height_cm <= 0.0
    ):
        return VERTICAL_OSC_HIGH_THRESHOLD, None, None
    scale = float(height_cm) / float(body_norm_length)
    # cm 임계를 정규화 등가로 역산해 per-stride classify 에 일관 적용.
    threshold_norm = VO_HIGH_THRESHOLD_CM / scale
    return threshold_norm, scale, VO_HIGH_THRESHOLD_CM


def analyze_vertical_oscillation(
    df: pd.DataFrame,
    strike_indices: dict,
    height_cm: float | None = None,
    body_norm_length: float | None = None,
) -> dict:
    """
    좌/우 각각 1 stride 단위로 진폭 계산 후 평균.

    Args:
        height_cm: 사용자 신장(cm). None 이면 정규화 임계 fallback.
        body_norm_length: 프레임 median nose~ankle 정규화 길이 (analyzer.body_scale).
            None 이면 정규화 임계 fallback.

    Returns:
        {
            "avg_value": float,                  # 정규화 평균 (항상 존재)
            "left_avg": float,
            "right_avg": float,
            "status": "high" | "good",
            "per_stride": [{..., "value", "value_cm" | None, "status", "foot"}],
            "avg_value_cm": float | None,        # cm-aware 모드일 때만 값
            "threshold_cm": float | None,        # cm-aware 모드일 때만 값
            "threshold_norm": float,             # 실제 적용된 정규화 임계
            "scale_cm_per_norm": float | None,   # cm-aware 모드일 때만 값
            "height_cm": float | None,
            "body_norm_length": float | None,
        }
    """
    threshold_norm, scale, threshold_cm = _resolve_threshold_norm(
        height_cm, body_norm_length
    )
    cm_mode = scale is not None

    per_stride: list[dict] = []

    def _process(side: str, col: str, strikes: np.ndarray) -> list[float]:
        values: list[float] = []
        for s in calculate_oscillation_per_stride(
            df[col].to_numpy(dtype=float), strikes
        ):
            status = classify_oscillation(s["value"], threshold=threshold_norm)
            entry = {
                **s,
                "status": status,
                "foot": side,
                "value_cm": (s["value"] * scale) if cm_mode else None,
            }
            per_stride.append(entry)
            values.append(s["value"])
        return values

    left_vals = _process("left", "left_hip_y", strike_indices["left"])
    right_vals = _process("right", "right_hip_y", strike_indices["right"])

    def _avg(xs: list[float]) -> float:
        return float(np.mean(xs)) if xs else float("nan")

    avg_value = _avg(left_vals + right_vals)
    overall_status = (
        "high"
        if (not np.isnan(avg_value) and avg_value > threshold_norm)
        else "good"
    )

    result = {
        "avg_value": avg_value,
        "left_avg": _avg(left_vals),
        "right_avg": _avg(right_vals),
        "status": overall_status,
        "per_stride": sorted(per_stride, key=lambda x: x["start_frame"]),
        "avg_value_cm": (avg_value * scale) if (cm_mode and not np.isnan(avg_value)) else None,
        "threshold_cm": threshold_cm,
        "threshold_norm": threshold_norm,
        "scale_cm_per_norm": scale,
        "height_cm": float(height_cm) if cm_mode else None,
        "body_norm_length": float(body_norm_length) if cm_mode else None,
    }
    if cm_mode:
        logger.info(
            "vertical osc (cm-aware): avg=%.4f norm (%.2f cm), threshold=%.2f cm, status=%s",
            avg_value, result["avg_value_cm"] or float("nan"), threshold_cm, overall_status,
        )
    else:
        logger.info(
            "vertical osc (fallback norm): avg=%.4f, threshold=%.4f, status=%s",
            avg_value, threshold_norm, overall_status,
        )
    return result


__all__ = [
    "calculate_oscillation_per_stride",
    "classify_oscillation",
    "analyze_vertical_oscillation",
]
