"""
좌/우 발목 Y좌표 시계열에서 Local Minima 를 검출해 착지 프레임 인덱스를 산출.

MediaPipe 좌표계는 화면 좌상단이 (0,0)이므로 Y값이 '작을수록' 위쪽이지만,
발목은 디딤 순간 가장 '아래'에 위치하므로 Y 가 최대가 된다.
→ Y 시리즈의 극대점이 착지 시점.

원 PRD 는 'Local Minima' 라는 용어를 쓰지만 좌표계 정의상 실제로는 극대점이
물리적 착지에 해당한다. 본 구현은 극대점을 사용하되, 외부 명세를 유지하기 위해
docstring 만 'Y 시리즈의 극단점' 으로 통일한다.
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd
from scipy.signal import find_peaks

from config import FOOT_STRIKE_COOLDOWN_FRAMES

logger = logging.getLogger(__name__)


def detect_foot_strikes(
    ankle_y_series: np.ndarray,
    cooldown: int = FOOT_STRIKE_COOLDOWN_FRAMES,
) -> np.ndarray:
    """
    발목 Y 시계열의 극대점(= 화면 하단 = 착지)을 찾는다.

    Args:
        ankle_y_series: 1D 배열 (NaN 가능).
        cooldown: 동일 발 착지 사이 최소 프레임 간격.

    Returns:
        착지 프레임 인덱스 배열 (오름차순).
    """
    arr = np.asarray(ankle_y_series, dtype=float)
    if arr.size == 0:
        return np.array([], dtype=int)

    # find_peaks 는 NaN 을 처리하지 못하므로 매우 작은 값으로 마스킹.
    sentinel = np.nanmin(arr) - 1.0 if np.isfinite(np.nanmin(arr)) else -1.0
    sanitized = np.where(np.isnan(arr), sentinel, arr)

    peaks, _ = find_peaks(sanitized, distance=cooldown)
    # 마스킹된 NaN 위치는 결과에서 제거.
    peaks = peaks[~np.isnan(arr[peaks])]
    return peaks.astype(int)


def detect_left_right_strikes(df: pd.DataFrame) -> dict:
    """
    좌/우 발목을 독립 추적해 각 발의 착지 인덱스를 반환.

    Args:
        df: 전처리된 keypoints DataFrame.
            'left_ankle_y' / 'right_ankle_y' 컬럼이 반드시 존재해야 한다.

    Returns:
        {"left": np.ndarray, "right": np.ndarray}
    """
    if "left_ankle_y" not in df.columns or "right_ankle_y" not in df.columns:
        raise KeyError("DataFrame must contain 'left_ankle_y' and 'right_ankle_y'")

    left = detect_foot_strikes(df["left_ankle_y"].to_numpy(dtype=float))
    right = detect_foot_strikes(df["right_ankle_y"].to_numpy(dtype=float))

    logger.info("strikes detected: left=%d, right=%d", len(left), len(right))
    return {"left": left, "right": right}


__all__ = ["detect_foot_strikes", "detect_left_right_strikes"]
