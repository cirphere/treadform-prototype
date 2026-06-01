"""
detect_foot_strikes 단위 테스트 (2026-05-29 신설).

기존 e2e 테스트는 synthetic_strikes 픽스처로 detection 을 우회 — cooldown
/ prominence / NaN 처리 동작이 명시 보호되지 않았다. 본 파일은:

- cooldown / min_prominence 동작 시그니처 명시
- config 기본값 (FOOT_STRIKE_COOLDOWN_FRAMES=20, FOOT_STRIKE_MIN_PROMINENCE=0.001)
  의 회귀 방지
- boundary / NaN 의 spurious peak 거름 동작 검증
"""
from __future__ import annotations

import numpy as np
import pytest

from analyzer.foot_strike_detector import detect_foot_strikes, detect_left_right_strikes
import pandas as pd
from config import FOOT_STRIKE_COOLDOWN_FRAMES, FOOT_STRIKE_MIN_PROMINENCE


def _sine_ankle_series(n_frames: int, n_strikes: int, amplitude: float = 0.1) -> np.ndarray:
    """주기적 sin 파 — 디딤 (peak) n_strikes 개의 발목 Y 시계열을 모사.
    peak 가 array 안쪽 (0.5, 1.5, ..., n_strikes-0.5 cycle) 에 위치하도록
    phase shift 해서 find_peaks 가 양 끝의 값을 못 잡는 동작에 안전하게.
    """
    t = np.linspace(0, n_strikes, n_frames)
    # peak 위치: t = 0.5, 1.5, ..., n_strikes - 0.5 (모두 [0, n_strikes] 안쪽).
    return 0.5 + amplitude * np.sin(2 * np.pi * t - np.pi / 2)


# ---------------------------------------------------------------------------
# Config 기본값 (회귀 방지)
# ---------------------------------------------------------------------------


def test_default_cooldown_is_20_frames():
    """60fps 기준 0.333s. stride cycle 의 절반 (Cavanagh 1989).
    실측 보정 (2026-05-29) 에 따른 10→20 변경 회귀 방지."""
    assert FOOT_STRIKE_COOLDOWN_FRAMES == 20


def test_default_min_prominence_is_0_001():
    """boundary spurious peak (정상 prom 의 1% 이하) 만 거르는 보수적 임계.
    실측 보정 (2026-05-29) 에 따른 신규 도입."""
    assert FOOT_STRIKE_MIN_PROMINENCE == pytest.approx(0.001)


# ---------------------------------------------------------------------------
# 기본 detection
# ---------------------------------------------------------------------------


class TestBasicDetection:
    def test_empty_array_returns_empty(self):
        result = detect_foot_strikes(np.array([], dtype=float))
        assert len(result) == 0

    def test_all_nan_returns_empty(self):
        result = detect_foot_strikes(np.full(60, np.nan))
        assert len(result) == 0

    def test_periodic_signal_finds_correct_peak_count(self):
        # 600 frames, 5 peaks → cooldown=20 와 정상 strike 간격 (120 frames) 모두 만족.
        y = _sine_ankle_series(n_frames=600, n_strikes=5)
        strikes = detect_foot_strikes(y)
        assert len(strikes) == 5

    def test_returns_int_dtype(self):
        y = _sine_ankle_series(n_frames=300, n_strikes=3)
        strikes = detect_foot_strikes(y)
        assert strikes.dtype.kind == "i"


# ---------------------------------------------------------------------------
# Cooldown 동작
# ---------------------------------------------------------------------------


class TestCooldown:
    def test_cooldown_rejects_too_close_peaks(self):
        # 2 frame 간격으로 2 peak 만들기 → cooldown=20 → 1개만 잡힘.
        y = np.full(100, 0.5)
        y[10] = 0.6
        y[12] = 0.6
        strikes = detect_foot_strikes(y, cooldown=20, min_prominence=0.0)
        assert len(strikes) == 1

    def test_custom_cooldown_allows_close_peaks(self):
        # cooldown=1 이면 2 frame 간격 두 peak 모두 잡힘.
        y = np.full(100, 0.5)
        y[10] = 0.6
        y[12] = 0.7  # 두 번째 peak 가 더 커야 cooldown=1 에서 둘 다 안전 검출.
        strikes = detect_foot_strikes(y, cooldown=1, min_prominence=0.0)
        assert len(strikes) == 2


# ---------------------------------------------------------------------------
# Prominence 동작 (실측 검증된 핵심 신규 기능)
# ---------------------------------------------------------------------------


class TestProminence:
    def test_low_prominence_peak_is_filtered(self):
        # 정상 peak (prom=0.1) + boundary spurious (prom=0.0005) 인 시리즈.
        y = np.full(200, 0.5)
        y[50] = 0.6   # 정상 peak, prom ≈ 0.1
        y[150] = 0.5005  # spurious peak, prom ≈ 0.0005

        strikes_default = detect_foot_strikes(y)  # min_prominence=0.001
        assert len(strikes_default) == 1
        assert strikes_default[0] == 50  # spurious 가 걸러짐

    def test_explicit_zero_prominence_keeps_all_peaks(self):
        y = np.full(200, 0.5)
        y[50] = 0.6
        y[150] = 0.5005
        strikes = detect_foot_strikes(y, min_prominence=0.0)
        assert len(strikes) == 2

    def test_prominence_threshold_above_normal_filters_normal_peaks(self):
        y = _sine_ankle_series(n_frames=600, n_strikes=5, amplitude=0.1)
        # amplitude=0.1 → prom 약 0.2. 임계 0.5 면 모두 거름.
        strikes = detect_foot_strikes(y, min_prominence=0.5)
        assert len(strikes) == 0


# ---------------------------------------------------------------------------
# NaN 처리
# ---------------------------------------------------------------------------


class TestNanHandling:
    def test_nan_positions_excluded_from_result(self):
        # peak 위치에 NaN 이면 검출 결과에서 빠져야 함.
        y = np.full(100, 0.5)
        y[30] = 0.6
        y[60] = np.nan
        strikes = detect_foot_strikes(y, min_prominence=0.0)
        assert 30 in strikes
        assert 60 not in strikes


# ---------------------------------------------------------------------------
# detect_left_right_strikes 통합
# ---------------------------------------------------------------------------


class TestLeftRightStrikes:
    def test_returns_left_right_keys(self):
        df = pd.DataFrame({
            "left_ankle_y": _sine_ankle_series(300, 3),
            "right_ankle_y": _sine_ankle_series(300, 3),
        })
        result = detect_left_right_strikes(df)
        assert set(result.keys()) == {"left", "right"}
        assert len(result["left"]) == 3
        assert len(result["right"]) == 3

    def test_raises_on_missing_columns(self):
        df = pd.DataFrame({"left_ankle_y": [0.5, 0.6, 0.5]})
        with pytest.raises(KeyError):
            detect_left_right_strikes(df)
