"""
좌우 비대칭 보조 지표.

비율 = |L - R| / max(L, R), 0 ≤ ratio ≤ 1.
ASYMMETRY_WARNING_THRESHOLD (기본 0.1 = 10%) 를 넘으면 경고.

is_warning 트리거 정책 (2026-05-16):
    - knee_angle 또는 oscillation 만 워닝 트리거에 참여.
    - strike_count_ratio 는 결과에 노출은 하되 트리거에서 제외 — 측면 촬영의
      far-side leg occlusion 이 dominant 노이즈이므로 단독 신호로 사용 시
      false positive 가 너무 많다 (4 pace 영상 동일 러너 정상 자세에서 diff=3
      다발). 진짜 비대칭(절뚝/비스듬런) 은 knee/osc 에 동반된다.
    - 좌/우 발 평균 visibility 차이가 큰 영상에서는 strike_count_ratio 자체를
      NaN 으로 대체해 결과 화면에도 "측정 불가" 로 노출.
"""
from __future__ import annotations

import logging

import numpy as np

from config import (
    ASYMMETRY_FOOT_VIS_DIFF_THRESHOLD,
    ASYMMETRY_WARNING_THRESHOLD,
)

logger = logging.getLogger(__name__)


def calculate_asymmetry_ratio(left_value: float, right_value: float) -> float:
    """
    Returns:
        |L - R| / max(L, R). 입력에 NaN 이 있거나 둘 다 0 이면 NaN.
    """
    if np.isnan(left_value) or np.isnan(right_value):
        return float("nan")
    denom = max(abs(left_value), abs(right_value))
    if denom == 0.0:
        return float("nan")
    return float(abs(left_value - right_value) / denom)


def analyze_asymmetry(
    strike_indices: dict,
    knee_result: dict,
    vertical_result: dict,
    foot_visibility: dict | None = None,
) -> dict:
    """
    Args:
        strike_indices: {"left": np.ndarray, "right": np.ndarray} 착지 프레임 인덱스.
        knee_result: analyze_knee_flexion 결과 (left_avg/right_avg 필요).
        vertical_result: analyze_vertical_oscillation 결과 (left_avg/right_avg 필요).
        foot_visibility: {"left": float, "right": float} 좌/우 발 평균 visibility.
            제공 시 |L−R| > ASYMMETRY_FOOT_VIS_DIFF_THRESHOLD 이면 strike_count_ratio 를
            NaN 으로 대체 (검출 신뢰도 비대칭으로 strike 차이가 의미 없는 경우).

    Returns:
        {
            "strike_count_ratio": float,   # 정보성 — 트리거 X (모듈 docstring 참조)
            "knee_angle_ratio": float,     # 트리거 O
            "oscillation_ratio": float,    # 트리거 O
            "is_warning": bool
        }
    """
    left_count = float(len(strike_indices["left"]))
    right_count = float(len(strike_indices["right"]))

    strike_ratio = calculate_asymmetry_ratio(left_count, right_count)

    # Visibility 가중: 좌/우 발 검출 신뢰도 차이가 크면 strike_ratio 신뢰 불가.
    if foot_visibility is not None:
        l_vis = float(foot_visibility.get("left", float("nan")))
        r_vis = float(foot_visibility.get("right", float("nan")))
        if (
            not np.isnan(l_vis)
            and not np.isnan(r_vis)
            and abs(l_vis - r_vis) > ASYMMETRY_FOOT_VIS_DIFF_THRESHOLD
        ):
            strike_ratio = float("nan")

    knee_ratio = calculate_asymmetry_ratio(
        knee_result.get("left_avg", float("nan")),
        knee_result.get("right_avg", float("nan")),
    )
    osc_ratio = calculate_asymmetry_ratio(
        vertical_result.get("left_avg", float("nan")),
        vertical_result.get("right_avg", float("nan")),
    )

    # 트리거는 knee/osc 만 — strike_count 는 정보성으로만 노출.
    knee_warn = not np.isnan(knee_ratio) and knee_ratio > ASYMMETRY_WARNING_THRESHOLD
    osc_warn = not np.isnan(osc_ratio) and osc_ratio > ASYMMETRY_WARNING_THRESHOLD
    is_warning = knee_warn or osc_warn

    result = {
        "strike_count_ratio": strike_ratio,
        "knee_angle_ratio": knee_ratio,
        "oscillation_ratio": osc_ratio,
        "is_warning": is_warning,
    }
    logger.info("asymmetry=%s", result)
    return result


__all__ = ["calculate_asymmetry_ratio", "analyze_asymmetry"]
