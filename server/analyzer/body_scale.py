"""
신체 정규화 길이 추정 (cm-aware 지표 환산용).

프레임별 nose ~ ankle 정규화 수직 거리의 median 을 "body_norm_length" 로 정의.
사용자 입력 height_cm 와 결합해 정규화 좌표 → 절대 cm 환산 스케일을 얻는다:

    scale_cm_per_norm = height_cm / body_norm_length
    metric_cm = metric_norm * scale_cm_per_norm

좌/우 ankle 중 화면상 더 아래쪽(=y 가 큰 쪽) 을 사용해 한쪽 occlusion 에 robust.
visibility 마스킹은 preprocessor 가 이미 NaN 으로 처리했다고 가정.
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


def compute_body_norm_length(df: pd.DataFrame) -> float:
    """
    프레임별 (max(left_ankle_y, right_ankle_y) - nose_y) 의 median.

    Returns:
        정규화 좌표 단위 신체 길이 (대략 0.3~0.8 사이 기대). 유효 프레임 0개 시 NaN.
    """
    required = ("nose_y", "left_ankle_y", "right_ankle_y")
    if not all(c in df.columns for c in required):
        logger.warning("body_norm_length: required columns missing (%s)", required)
        return float("nan")

    nose_y = df["nose_y"].to_numpy(dtype=float)
    la_y = df["left_ankle_y"].to_numpy(dtype=float)
    ra_y = df["right_ankle_y"].to_numpy(dtype=float)

    # 좌/우 ankle 중 더 아래쪽(y 큰 값). 한쪽이 NaN 이어도 다른쪽이 살아 있으면 통과.
    ankle_y = np.fmax(la_y, ra_y)

    body_len = ankle_y - nose_y  # 화면 좌상단 (0,0), y 증가 = 아래 → 양수.

    valid = np.isfinite(body_len) & (body_len > 0.0)
    if not np.any(valid):
        logger.warning("body_norm_length: no valid frame (nose+ankle visibility)")
        return float("nan")

    value = float(np.median(body_len[valid]))
    logger.info(
        "body_norm_length: %.4f (valid frames %d/%d)",
        value, int(np.sum(valid)), int(body_len.size),
    )
    return value


__all__ = ["compute_body_norm_length"]
