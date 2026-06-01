"""
좌표 시계열 전처리.

순서가 중요하다 (PRD-1 흔한 함정 #4):
    1) Forward Fill (max_frames 초과 시 NaN 유지)
    2) Exponential Moving Average

EMA 를 먼저 적용하면 NaN 이 후속 값으로 전파되므로 반드시 FF 가 먼저.
visibility 컬럼은 원본을 유지한다 (분석 단계에서 신뢰도 필터링 용도).
"""
from __future__ import annotations

import logging
import math

import numpy as np
import pandas as pd

from analyzer.filters import one_euro_filter_array
from config import (
    EMA_ALPHA,
    HAMPEL_THRESHOLD_K,
    HAMPEL_WINDOW,
    LR_SWAP_MIN_GAIN,
    LR_SWAP_RATIO,
    MAX_FORWARD_FILL_FRAMES,
    ONE_EURO_BETA,
    ONE_EURO_D_CUTOFF,
    ONE_EURO_MIN_CUTOFF,
    TARGET_FPS,
    VISIBILITY_THRESHOLD,
)

logger = logging.getLogger(__name__)


def forward_fill_with_limit(
    series: np.ndarray,
    max_frames: int = MAX_FORWARD_FILL_FRAMES,
) -> np.ndarray:
    """
    결측값을 직전 유효값으로 채우되, 연속 결측이 max_frames 를 초과하면 NaN 유지.

    Args:
        series: 1D float 배열 (NaN 허용).
        max_frames: 허용 최대 연속 결측 길이.

    Returns:
        같은 길이의 1D 배열.
    """
    arr = np.asarray(series, dtype=float).copy()
    n = arr.size
    if n == 0:
        return arr

    last_valid = np.nan
    streak = 0  # 현재 결측 streak 길이 (마지막 유효값 이후).

    for i in range(n):
        v = arr[i]
        if not np.isnan(v):
            last_valid = v
            streak = 0
            continue

        if np.isnan(last_valid):
            # 시리즈 시작부 결측 → 채울 값 없음.
            continue

        streak += 1
        if streak <= max_frames:
            arr[i] = last_valid
        # 초과 시 NaN 유지. last_valid 도 그대로 둬서 추후 회복 시 다시 사용 가능.

    return arr


def exponential_moving_average(
    series: np.ndarray,
    alpha: float = EMA_ALPHA,
) -> np.ndarray:
    """
    EMA 평활화. y_t = α·x_t + (1-α)·y_{t-1}.

    NaN 은 그대로 유지하며, NaN 직후의 첫 유효 샘플은 시드로 사용.

    Args:
        series: 1D 배열.
        alpha: 평활 계수 (0~1).

    Returns:
        평활된 배열.
    """
    arr = np.asarray(series, dtype=float)
    n = arr.size
    out = np.full(n, np.nan, dtype=float)
    prev = np.nan
    for i in range(n):
        x = arr[i]
        if np.isnan(x):
            prev = np.nan
            continue
        if np.isnan(prev):
            out[i] = x
        else:
            out[i] = alpha * x + (1.0 - alpha) * prev
        prev = out[i]
    return out


_VISIBILITY_SUFFIX = "_visibility"
_COORD_SUFFIXES = ("_x", "_y", "_z")

# 정규분포 가정 하 σ ≈ 1.4826 × MAD.
_MAD_TO_SIGMA = 1.4826


def hampel_filter(
    series: np.ndarray,
    window: int = HAMPEL_WINDOW,
    k: float = HAMPEL_THRESHOLD_K,
) -> np.ndarray:
    """
    Hampel 필터로 시계열의 고립된 outlier 를 중앙값으로 대체.

    각 프레임 i 에 대해 [i - w, i + w] 윈도우 (w = window // 2) 의 중간값(median)과
    MAD(Median Absolute Deviation) 를 계산하고,
        |x[i] - median| > k * 1.4826 * MAD
    이면 x[i] 를 median 으로 교체. NaN 은 통계에 포함하지 않으며 NaN 자체는 그대로 둔다.

    Args:
        series: 1D 배열 (NaN 허용).
        window: 윈도우 크기 (홀수 권장). 기본 5.
        k: 임계 배수. 기본 3 (정규분포 가정의 3σ 등가).

    Returns:
        같은 길이의 1D 배열. spike 만 교체되며 정상 값은 그대로.
    """
    arr = np.asarray(series, dtype=float).copy()
    n = arr.size
    if n == 0 or window < 3:
        return arr

    half = window // 2
    out = arr.copy()
    for i in range(n):
        if np.isnan(arr[i]):
            continue
        lo = max(0, i - half)
        hi = min(n, i + half + 1)
        win = arr[lo:hi]
        win = win[~np.isnan(win)]
        if win.size < 3:
            continue
        med = float(np.median(win))
        mad = float(np.median(np.abs(win - med)))
        if mad == 0.0:
            # 윈도우 내 변동이 전혀 없는데 현재 값만 다르면 그 자체로 outlier.
            if arr[i] != med:
                out[i] = med
            continue
        threshold = k * _MAD_TO_SIGMA * mad
        if abs(arr[i] - med) > threshold:
            out[i] = med
    return out


def mask_low_visibility(
    df: pd.DataFrame, threshold: float = VISIBILITY_THRESHOLD
) -> pd.DataFrame:
    """
    landmark 별 visibility 가 threshold 미만이면 해당 landmark 의 x/y/z 를 NaN 으로 마스킹.

    pose_extractor 는 raw 좌표만 저장하므로 (가시화 친화), 분석 파이프라인 입장의
    신뢰도 필터링은 이 함수에서 일괄 수행한다.

    Args:
        df: extract_pose_series 결과 DataFrame.
        threshold: 이 미만이면 결측 처리.

    Returns:
        새 DataFrame.
    """
    out = df.copy()
    vis_cols = [c for c in out.columns if c.endswith(_VISIBILITY_SUFFIX)]
    for vc in vis_cols:
        base = vc[: -len(_VISIBILITY_SUFFIX)]  # 예: "left_hip"
        mask = out[vc].to_numpy(dtype=float) < threshold
        for suf in _COORD_SUFFIXES:
            col = f"{base}{suf}"
            if col in out.columns:
                arr = out[col].to_numpy(dtype=float, copy=True)
                arr[mask] = float("nan")
                out[col] = arr
    return out


# 좌/우 identity 보정 대상 관절. 다리 + 골반 묶음으로 함께 swap.
_LR_JOINT_GROUP = ("hip", "knee", "ankle", "heel", "foot_index")


def correct_lr_swaps(
    df: pd.DataFrame,
    min_gain: float = LR_SWAP_MIN_GAIN,
    ratio: float = LR_SWAP_RATIO,
) -> tuple[pd.DataFrame, int]:
    """
    측면 자기-가림으로 mediapipe 가 좌/우 다리 landmark 를 뒤바꾼 프레임을 탐지/교환.

    각 프레임 t 에서, 직전 프레임의 좌/우 좌표 대비 다음 두 비용을 계산:
        normal_cost = Σ dist(L_t, L_{t-1}) + dist(R_t, R_{t-1})
        swap_cost   = Σ dist(L_t, R_{t-1}) + dist(R_t, L_{t-1})
    (Σ 는 _LR_JOINT_GROUP 의 (x,y) 거리 합)

    swap_cost 가 normal_cost 보다 min_gain 이상 작으면 해당 프레임의 좌/우를 일괄 교환.
    교환은 _LR_JOINT_GROUP 의 x/y/z/visibility 모두에 일관 적용 (다리 단위).

    Args:
        df: extract_pose_series 결과 (mask 후).
        min_gain: 거리 감소가 이 값 이상일 때만 swap. 작은 노이즈로 인한 오발견 방지.

    Returns:
        (보정된 DataFrame, 교환된 프레임 수)
    """
    out = df.copy()
    n = len(out)
    if n < 2:
        return out, 0

    # 컬럼 캐시. 둘 다 존재하는 관절만 처리.
    coord_suf = ("_x", "_y", "_z", "_visibility")
    available_joints: list[str] = []
    left_cols: dict[str, list[str]] = {}
    right_cols: dict[str, list[str]] = {}
    for j in _LR_JOINT_GROUP:
        lc = [f"left_{j}{s}" for s in coord_suf]
        rc = [f"right_{j}{s}" for s in coord_suf]
        if all(c in out.columns for c in lc) and all(c in out.columns for c in rc):
            available_joints.append(j)
            left_cols[j] = lc
            right_cols[j] = rc

    if not available_joints:
        return out, 0

    swaps = 0
    prev_left = {j: _xy_safe(out, 0, left_cols[j]) for j in available_joints}
    prev_right = {j: _xy_safe(out, 0, right_cols[j]) for j in available_joints}

    for i in range(1, n):
        cur_left = {j: _xy_safe(out, i, left_cols[j]) for j in available_joints}
        cur_right = {j: _xy_safe(out, i, right_cols[j]) for j in available_joints}

        normal_sum = 0.0
        swap_sum = 0.0
        count = 0
        for j in available_joints:
            cl, cr = cur_left[j], cur_right[j]
            pl, pr = prev_left[j], prev_right[j]
            if cl is None or cr is None or pl is None or pr is None:
                continue
            normal_sum += _dist(cl, pl) + _dist(cr, pr)
            swap_sum += _dist(cl, pr) + _dist(cr, pl)
            count += 1

        # 평균 (관절 1개당, L+R 합산) 비용.
        normal_avg = normal_sum / count if count else float("inf")
        swap_avg = swap_sum / count if count else float("inf")
        gain = normal_avg - swap_avg

        # swap 조건: (1) 최소 3관절 매칭, (2) 평균이 충분히 줄고,
        # (3) 비율도 충분히 작아야 (절대 차 + 상대 차 양쪽 조건).
        swap_ok = (
            count >= 3
            and gain > min_gain
            and (normal_avg > 0)
            and (swap_avg / normal_avg) < ratio
        )

        if swap_ok:
            for j in available_joints:
                for lc, rc in zip(left_cols[j], right_cols[j]):
                    lv = out.at[i, lc]
                    rv = out.at[i, rc]
                    out.at[i, lc] = rv
                    out.at[i, rc] = lv
            for j in available_joints:
                prev_left[j] = cur_right[j]
                prev_right[j] = cur_left[j]
            swaps += 1
        else:
            for j in available_joints:
                if cur_left[j] is not None:
                    prev_left[j] = cur_left[j]
                if cur_right[j] is not None:
                    prev_right[j] = cur_right[j]

    if swaps:
        logger.info("L/R swap correction: %d frames", swaps)
    return out, swaps


def _xy_safe(df: pd.DataFrame, idx: int, cols: list[str]) -> tuple[float, float] | None:
    """(x, y) 반환. NaN 이면 None."""
    x = float(df.at[idx, cols[0]])
    y = float(df.at[idx, cols[1]])
    if np.isnan(x) or np.isnan(y):
        return None
    return x, y


def _dist(a: tuple[float, float], b: tuple[float, float]) -> float:
    return math.sqrt((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2)


def despike_pose_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """
    visibility 마스킹 + Hampel spike 제거 + 좌/우 swap 보정만 적용.

    디버그 가시화용: One Euro 지연 없이 lag 0 좌표를 얻되 단일 프레임 spike 와
    좌/우 ID 혼동은 보정. 분석 파이프라인은 이 위에 forward fill + One Euro 적용.
    """
    out = mask_low_visibility(df)
    for col in out.columns:
        if not col.endswith(_COORD_SUFFIXES):
            continue
        if col.endswith(_VISIBILITY_SUFFIX):
            continue
        out[col] = hampel_filter(out[col].to_numpy(dtype=float))
    out, _ = correct_lr_swaps(out)
    out.attrs.update(df.attrs)
    return out


def preprocess_pose_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """
    분석용 전처리 파이프라인 (상용 표준 기법 조합):
        1) visibility < threshold 좌표를 NaN 마스킹
        2) Hampel 필터로 단일 프레임 spike 제거 (중앙값 대체)
        3) 좌/우 identity 보정 (자기-가림으로 인한 swap 교정)
        4) Forward Fill (max_frames 초과 시 NaN 유지)
        5) One Euro Filter — 적응형 저역통과 (정지=강한 평활화, 빠른 동작=lag 0)
           기존 EMA 를 대체. MediaPipe / Apple Vision 등이 사용하는 표준.

    visibility / frame_idx / timestamp_sec 컬럼은 변경하지 않는다.

    Args:
        df: extract_pose_series 가 반환한 (raw) DataFrame.

    Returns:
        새 DataFrame (원본 attrs 유지).
    """
    fps = float(df.attrs.get("fps", TARGET_FPS))

    out = mask_low_visibility(df)
    # 1차 spike 제거.
    for col in out.columns:
        if not col.endswith(_COORD_SUFFIXES):
            continue
        if col.endswith(_VISIBILITY_SUFFIX):
            continue
        out[col] = hampel_filter(out[col].to_numpy(dtype=float))

    # 2차 좌/우 identity 보정.
    out, swap_count = correct_lr_swaps(out)

    # 3차 forward fill + One Euro.
    for col in out.columns:
        if not col.endswith(_COORD_SUFFIXES):
            continue
        if col.endswith(_VISIBILITY_SUFFIX):
            continue
        filled = forward_fill_with_limit(out[col].to_numpy(dtype=float))
        smoothed = one_euro_filter_array(
            filled,
            fps=fps,
            min_cutoff=ONE_EURO_MIN_CUTOFF,
            beta=ONE_EURO_BETA,
            d_cutoff=ONE_EURO_D_CUTOFF,
        )
        out[col] = smoothed

    out.attrs.update(df.attrs)
    logger.info(
        "preprocess done: rows=%d, cols=%d, lr_swaps=%d",
        len(out),
        len(out.columns),
        swap_count,
    )
    return out


__all__ = [
    "forward_fill_with_limit",
    "exponential_moving_average",
    "hampel_filter",
    "mask_low_visibility",
    "correct_lr_swaps",
    "despike_pose_dataframe",
    "preprocess_pose_dataframe",
]
