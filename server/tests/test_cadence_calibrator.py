"""
cadence_calibrator 단위 테스트 (Phase 1, 2026-05-28).

밴드 경계, 신장 시프트, hint/deviation 분류, None 경로.
"""
from __future__ import annotations

import pytest

from analyzer.cadence_calibrator import (
    calculate_expected_cadence_range,
    classify_cadence,
)
from config import (
    CADENCE_BANDS_170CM,
    CADENCE_HEIGHT_SHIFT_SPM_PER_CM,
    CADENCE_HINT_HIGH,
    CADENCE_HINT_LOW,
    CADENCE_HINT_OPTIMAL,
)


# ---------------------------------------------------------------------------
# calculate_expected_cadence_range
# ---------------------------------------------------------------------------


class TestExpectedRange:
    def test_pace_5_30_at_170cm_returns_168_180(self):
        # 5:30/km = 330 sec/km, 경계 inclusive 로 [330, 390) 밴드.
        rng = calculate_expected_cadence_range(330, 170)
        assert rng == (168, 180)

    def test_pace_6_30_at_170cm_falls_into_jog_band(self):
        # 6:30 = 390 sec/km → [390, inf) 밴드.
        rng = calculate_expected_cadence_range(390, 170)
        assert rng == (162, 175)

    def test_pace_4_30_at_170cm_falls_into_tempo_band(self):
        # 4:30 = 270 sec/km → [270, 330).
        rng = calculate_expected_cadence_range(270, 170)
        assert rng == (175, 188)

    def test_pace_fast_at_170cm_returns_race_band(self):
        # 4:00 = 240 sec/km → [0, 270).
        rng = calculate_expected_cadence_range(240, 170)
        assert rng == (182, 196)

    def test_height_taller_shifts_band_down(self):
        # 190cm = 170 + 20cm → -10 spm shift.
        rng = calculate_expected_cadence_range(330, 190)
        assert rng == (168 - 10, 180 - 10)

    def test_height_shorter_shifts_band_up(self):
        # 150cm = 170 - 20cm → +10 spm shift.
        rng = calculate_expected_cadence_range(330, 150)
        assert rng == (168 + 10, 180 + 10)

    def test_height_shift_uses_config_constant(self):
        # 시프트 상수 변경에 회귀 안 되도록 명시 검증.
        assert CADENCE_HEIGHT_SHIFT_SPM_PER_CM == 0.5

    def test_default_height_when_none(self):
        rng_default = calculate_expected_cadence_range(330, None)
        rng_170 = calculate_expected_cadence_range(330, 170)
        assert rng_default == rng_170

    def test_default_height_when_invalid(self):
        # 0 또는 음수 height → 기본값.
        rng_zero = calculate_expected_cadence_range(330, 0)
        rng_default = calculate_expected_cadence_range(330, None)
        assert rng_zero == rng_default

    def test_returns_none_for_missing_pace(self):
        assert calculate_expected_cadence_range(None, 170) is None

    def test_returns_none_for_nonpositive_pace(self):
        assert calculate_expected_cadence_range(0, 170) is None
        assert calculate_expected_cadence_range(-5, 170) is None

    def test_band_table_covers_zero_to_infinity(self):
        # 모든 양수 pace 가 어떤 밴드에 매칭되어야 한다 (테이블 정합성).
        for pace in (1, 100, 269.99, 270, 329.99, 330, 389.99, 390, 1000):
            assert calculate_expected_cadence_range(pace, 170) is not None

    def test_band_table_lo_lt_hi(self):
        # 테이블 형식 sanity.
        for lo_sec, hi_sec, spm_lo, spm_hi in CADENCE_BANDS_170CM:
            assert lo_sec < hi_sec
            assert spm_lo < spm_hi


# ---------------------------------------------------------------------------
# classify_cadence
# ---------------------------------------------------------------------------


class TestClassifyCadence:
    def test_actual_inside_band_is_optimal(self):
        result = classify_cadence(175, 168, 180)
        assert result["hint"] == CADENCE_HINT_OPTIMAL
        assert result["deviation_pct"] == 0.0

    def test_actual_at_lower_bound_is_optimal(self):
        result = classify_cadence(168, 168, 180)
        assert result["hint"] == CADENCE_HINT_OPTIMAL

    def test_actual_at_upper_bound_is_optimal(self):
        result = classify_cadence(180, 168, 180)
        assert result["hint"] == CADENCE_HINT_OPTIMAL

    def test_actual_below_band_is_low(self):
        result = classify_cadence(160, 168, 180)
        assert result["hint"] == CADENCE_HINT_LOW
        # (168-160)/168 ≈ 4.76%.
        assert result["deviation_pct"] == pytest.approx(4.8, abs=0.1)

    def test_actual_above_band_is_high(self):
        result = classify_cadence(195, 168, 180)
        assert result["hint"] == CADENCE_HINT_HIGH
        # (195-180)/180 ≈ 8.33%.
        assert result["deviation_pct"] == pytest.approx(8.3, abs=0.1)

    def test_zero_actual_returns_optimal_safety(self):
        # 측정 실패/0 은 평가 무의미 — optimal 로 silent (warning 트리거 회피).
        result = classify_cadence(0, 168, 180)
        assert result["hint"] == CADENCE_HINT_OPTIMAL

    def test_invalid_range_returns_optimal_safety(self):
        # lo > hi 같은 비정상 입력에도 폭주 안 됨.
        result = classify_cadence(175, 180, 168)
        assert result["hint"] == CADENCE_HINT_OPTIMAL
