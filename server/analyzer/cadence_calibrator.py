"""
Cadence pace-aware 보정 (Phase 0/1, 2026-05-28).

사용자 입력 pace (sec/km) + height (cm) 로 개인별 기대 cadence 범위를 산출하고,
측정 cadence (foot strikes / duration) 가 그 밴드 안인지 분류한다.

밴드와 신장 시프트 상수는 config.CADENCE_BANDS_170CM / CADENCE_HEIGHT_SHIFT_SPM_PER_CM
에서 관리. 절대 임계 부재의 약점 (개인차) 은 [[project-current-step]] 노트 참조 —
일반 통념을 따르되 정보성 (info) 으로만 노출하고 confidence/warning 등급에는
영향 주지 않는다.
"""
from __future__ import annotations

import logging

from config import (
    CADENCE_BANDS_170CM,
    CADENCE_HEIGHT_SHIFT_SPM_PER_CM,
    CADENCE_HINT_HIGH,
    CADENCE_HINT_LOW,
    CADENCE_HINT_OPTIMAL,
)

logger = logging.getLogger(__name__)


_DEFAULT_HEIGHT_CM = 170.0


def _band_for_pace(pace_sec_per_km: float) -> tuple[int, int]:
    """pace (sec/km) 가 속하는 명목 (170cm 기준) 밴드 반환."""
    for lo_sec, hi_sec, spm_lo, spm_hi in CADENCE_BANDS_170CM:
        if lo_sec <= pace_sec_per_km < hi_sec:
            return spm_lo, spm_hi
    # 모든 밴드가 0~inf 를 커버하지만 안전망.
    return CADENCE_BANDS_170CM[0][2], CADENCE_BANDS_170CM[0][3]


def calculate_expected_cadence_range(
    pace_sec_per_km: float | None,
    height_cm: float | None = None,
) -> tuple[int, int] | None:
    """
    pace + height → 기대 cadence (spm) 범위 (lo, hi).

    pace 미입력/비양수 시 None 반환 — 호출측이 cadence 평가 skip.
    height 미입력 시 170cm 기본값.

    신장 보정:
        shift = -(height_cm - 170) * CADENCE_HEIGHT_SHIFT_SPM_PER_CM
        키 ↑ → expected ↓ (긴 stride 보상)
    """
    if pace_sec_per_km is None or pace_sec_per_km <= 0:
        return None
    h = float(height_cm) if (height_cm is not None and height_cm > 0) else _DEFAULT_HEIGHT_CM

    base_lo, base_hi = _band_for_pace(float(pace_sec_per_km))
    shift = -(h - _DEFAULT_HEIGHT_CM) * CADENCE_HEIGHT_SHIFT_SPM_PER_CM
    return round(base_lo + shift), round(base_hi + shift)


def classify_cadence(
    actual_spm: float,
    expected_lo: int,
    expected_hi: int,
) -> dict:
    """
    측정 cadence vs 기대 범위.

    Returns:
        {
            "hint": "optimal" | "low" | "high",
            "deviation_pct": float,   # optimal 이면 0, 아니면 가장 가까운 경계 대비 %
        }
    """
    if actual_spm <= 0 or expected_hi <= 0 or expected_lo > expected_hi:
        return {"hint": CADENCE_HINT_OPTIMAL, "deviation_pct": 0.0}

    if expected_lo <= actual_spm <= expected_hi:
        return {"hint": CADENCE_HINT_OPTIMAL, "deviation_pct": 0.0}

    if actual_spm < expected_lo:
        dev = (expected_lo - actual_spm) / expected_lo * 100.0
        return {"hint": CADENCE_HINT_LOW, "deviation_pct": round(dev, 1)}

    dev = (actual_spm - expected_hi) / expected_hi * 100.0
    return {"hint": CADENCE_HINT_HIGH, "deviation_pct": round(dev, 1)}


__all__ = [
    "calculate_expected_cadence_range",
    "classify_cadence",
]
