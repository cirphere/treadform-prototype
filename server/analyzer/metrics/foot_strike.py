"""
Foot Strike 각도 지표.

발뒤꿈치(HEEL) → 발끝(FOOT_INDEX) 벡터의 수평 기준 기울기(°)를 산출.

좌표계: 화면 좌상단이 (0,0), Y 가 클수록 화면 아래.
진행 방향 무관: 러너가 화면 좌→우 / 우→좌 어느 쪽으로 달리든 동일한
발 기울기 측정값을 얻기 위해 dx 의 절대값을 사용한다. (이전 구현이
좌→우 진행만 가정해 우→좌 영상에서 모든 각도가 ±170° 로 빠지는 버그
2026-05-15 수정)

부호 정의 (러닝 메카닉스 기준):
    발끝이 발뒤꿈치보다 화면상 위쪽 (dy<0, 발이 들림) → 양수 → heel strike 경향
        러닝 메카닉스: heel strike 는 dorsiflexion (발끝 위로 당김) 상태에서
        뒤꿈치로 먼저 닿는 자세.
    발끝이 발뒤꿈치보다 화면상 아래쪽 (dy>0, 발이 처짐) → 음수 → forefoot 경향
        plantarflexion (발끝 아래) 상태에서 앞꿈치로 차는 자세.

판정:
    angle > HEEL_STRIKE_THRESHOLD     → heel_strike 🔴
    angle < FOREFOOT_STRIKE_THRESHOLD → forefoot_strike 🟡
    그 외                              → mid_foot_strike 🟢

분류 cutoff 0° 는 Altman & Davis 2012 (Gait Posture 35(2):298-300) 표준.
임계 ±3° 는 2D 영상의 perspective + 발 길이 정규화 노이즈에 대한 안전 마진
(임상 분류 관행에 정합, PRD-2 §R2).
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from config import FOREFOOT_STRIKE_THRESHOLD, HEEL_STRIKE_THRESHOLD

logger = logging.getLogger(__name__)


def calculate_foot_strike_angle(
    heel: np.ndarray, foot_index: np.ndarray
) -> float:
    """
    heel → foot_index 벡터의 수평 기준 각도(°). 진행 방향 무관.

    부호 정의 (모듈 docstring 참조):
        - 발끝이 발뒤꿈치보다 화면상 위쪽 → 양수 → heel strike 경향 (발 들림).
        - 발끝이 발뒤꿈치보다 화면상 아래쪽 → 음수 → forefoot 경향 (발 처짐).
    """
    heel = np.asarray(heel, dtype=float)
    foot_index = np.asarray(foot_index, dtype=float)
    if np.any(np.isnan(heel)) or np.any(np.isnan(foot_index)):
        return float("nan")
    dx = foot_index[0] - heel[0]
    dy = foot_index[1] - heel[1]
    if dx == 0.0 and dy == 0.0:
        return float("nan")
    # 화면 Y 가 아래로 갈수록 커지므로 -dy 가 위쪽 방향.
    # dx 의 절대값을 사용해 좌→우 / 우→좌 진행 모두에서 동일 결과.
    return float(np.degrees(np.arctan2(-dy, abs(dx))))


def classify_foot_strike(angle: float) -> str:
    """
    Returns:
        "heel_strike" | "mid_foot_strike" | "forefoot_strike"

    임계값 비교는 strict (>, <). 임계값과 정확히 같은 값은 mid_foot_strike.
    """
    if np.isnan(angle):
        return "mid_foot_strike"
    if angle > HEEL_STRIKE_THRESHOLD:
        return "heel_strike"
    if angle < FOREFOOT_STRIKE_THRESHOLD:
        return "forefoot_strike"
    return "mid_foot_strike"


def _xy(df: pd.DataFrame, side: str, name: str, frame: int) -> np.ndarray:
    return np.array(
        [df.at[frame, f"{side}_{name}_x"], df.at[frame, f"{side}_{name}_y"]],
        dtype=float,
    )


def analyze_foot_strike(df: pd.DataFrame, strike_indices: dict) -> dict:
    """
    좌/우 착지 프레임마다 발 각도 계산 + 분류.

    Returns:
        {
            "status_counts": {"heel": int, "midfoot": int, "forefoot": int},
            "per_strike": [{"frame": int, "angle": float, "status": str, "foot": str}]
        }
    """
    per_strike: list[dict] = []
    counts = {"heel": 0, "midfoot": 0, "forefoot": 0}

    for side, frames in (("left", strike_indices["left"]), ("right", strike_indices["right"])):
        for f in frames:
            f = int(f)
            heel = _xy(df, side, "heel", f)
            foot_index = _xy(df, side, "foot_index", f)
            angle = calculate_foot_strike_angle(heel, foot_index)
            status = classify_foot_strike(angle)
            per_strike.append(
                {"frame": f, "angle": angle, "status": status, "foot": side}
            )
            if status == "heel_strike":
                counts["heel"] += 1
            elif status == "forefoot_strike":
                counts["forefoot"] += 1
            else:
                counts["midfoot"] += 1

    result = {
        "status_counts": counts,
        "per_strike": sorted(per_strike, key=lambda x: x["frame"]),
    }
    logger.info("foot strike counts=%s", counts)
    return result


__all__ = [
    "calculate_foot_strike_angle",
    "classify_foot_strike",
    "analyze_foot_strike",
]
