"""
PRD-2 메트릭 단위 테스트.

경계 케이스 (Borderline 우선 판정) + 합성 데이터 통합 시나리오.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from analyzer.metrics.asymmetry import (
    analyze_asymmetry,
    calculate_asymmetry_ratio,
)
from analyzer.metrics.foot_strike import (
    analyze_foot_strike,
    calculate_foot_strike_angle,
    classify_foot_strike,
)
from analyzer.metrics.knee_flexion import (
    analyze_knee_flexion,
    calculate_knee_angle,
    classify_knee_status,
)
from analyzer.metrics.overstriding import (
    analyze_overstriding,
    calculate_overstride_distance,
    classify_overstride,
)
from analyzer.metrics.vertical_osc import (
    analyze_vertical_oscillation,
    calculate_oscillation_per_stride,
    classify_oscillation,
)
from analyzer.body_scale import compute_body_norm_length
from config import (
    ASYMMETRY_FOOT_VIS_DIFF_THRESHOLD,
    ASYMMETRY_WARNING_THRESHOLD,
    HEEL_STRIKE_THRESHOLD,
    KNEE_BORDERLINE_TOLERANCE,
    KNEE_STIFF_THRESHOLD,
    OVERSTRIDE_THRESHOLD,
    VERTICAL_OSC_HIGH_THRESHOLD,
    VO_HIGH_THRESHOLD_CM,
)


# ---------------------------------------------------------------------------
# 합성 데이터 픽스처
# ---------------------------------------------------------------------------
LANDMARKS = [
    "left_hip",
    "right_hip",
    "left_knee",
    "right_knee",
    "left_ankle",
    "right_ankle",
    "left_heel",
    "right_heel",
    "left_foot_index",
    "right_foot_index",
]


def _empty_frame_row(frame_idx: int, fps: float = 30.0) -> dict:
    row = {"frame_idx": frame_idx, "timestamp_sec": frame_idx / fps}
    for lm in LANDMARKS:
        row[f"{lm}_x"] = 0.5
        row[f"{lm}_y"] = 0.5
        row[f"{lm}_z"] = 0.0
        row[f"{lm}_visibility"] = 1.0
    return row


@pytest.fixture
def synthetic_running_df() -> pd.DataFrame:
    """
    이상적인 러닝 100프레임 합성 데이터.
    - 무릎: hip(0.5, 0.4), knee(0.5, 0.6), ankle(0.5+ε, 0.8) → 약 175° (stiff 근방)
      → borderline 으로 떨어지지 않도록 살짝 굽힘.
    - hip Y 는 30프레임 주기 sin 으로 약 0.04 진폭 (good_oscillation).
    """
    n = 100
    rows = [_empty_frame_row(i) for i in range(n)]
    for i, row in enumerate(rows):
        phase = 2 * math.pi * i / 30.0
        hip_y = 0.40 + 0.02 * math.sin(phase)  # 진폭 0.04 → good
        # 좌/우 골반.
        row["left_hip_y"] = hip_y
        row["right_hip_y"] = hip_y
        row["left_hip_x"] = 0.50
        row["right_hip_x"] = 0.50
        # 무릎: 약간 굽힌 150° 근방. hip-knee-ankle 일직선에서 knee 만 살짝 앞으로.
        for side in ("left", "right"):
            row[f"{side}_knee_x"] = 0.55
            row[f"{side}_knee_y"] = 0.60
            row[f"{side}_ankle_x"] = 0.52  # 골반 대비 0.02 → good_stride
            row[f"{side}_ankle_y"] = 0.80
            # mid foot strike: heel 과 foot_index 가 거의 같은 Y.
            row[f"{side}_heel_x"] = 0.50
            row[f"{side}_heel_y"] = 0.82
            row[f"{side}_foot_index_x"] = 0.56
            row[f"{side}_foot_index_y"] = 0.82
    df = pd.DataFrame(rows)
    df.attrs["fps"] = 30.0
    return df


@pytest.fixture
def synthetic_strikes() -> dict:
    """좌발 10/40/70, 우발 25/55/85 프레임에 착지."""
    return {
        "left": np.array([10, 40, 70], dtype=int),
        "right": np.array([25, 55, 85], dtype=int),
    }


# ---------------------------------------------------------------------------
# Knee Flexion
# ---------------------------------------------------------------------------
class TestKneeFlexion:
    def test_calculate_knee_angle_straight_leg_is_180(self):
        hip = np.array([0.5, 0.3])
        knee = np.array([0.5, 0.6])
        ankle = np.array([0.5, 0.9])
        angle = calculate_knee_angle(hip, knee, ankle)
        assert angle == pytest.approx(180.0, abs=1e-6)

    def test_calculate_knee_angle_right_angle(self):
        hip = np.array([0.5, 0.5])
        knee = np.array([0.5, 1.0])
        ankle = np.array([1.0, 1.0])
        angle = calculate_knee_angle(hip, knee, ankle)
        assert angle == pytest.approx(90.0, abs=1e-6)

    def test_calculate_knee_angle_nan_input(self):
        hip = np.array([np.nan, 0.3])
        knee = np.array([0.5, 0.6])
        ankle = np.array([0.5, 0.9])
        assert math.isnan(calculate_knee_angle(hip, knee, ankle))

    def test_knee_at_stiff_threshold_is_borderline(self):
        # 정확히 stiff 임계값 (165°) → ±tol 범위 안 → borderline.
        assert classify_knee_status(float(KNEE_STIFF_THRESHOLD)) == "borderline"

    def test_knee_above_stiff_border_is_stiff(self):
        # stiff 임계 + tol 초과 (168° 초과) → stiff.
        assert classify_knee_status(168.0 + 0.01) == "stiff_knee"

    def test_knee_at_150_is_good(self):
        assert classify_knee_status(150.0) == "good_flexion"

    def test_knee_at_130_is_over_bent(self):
        # 140 - tol 미만 영역 → over_bent.
        assert classify_knee_status(130.0) == "over_bent"

    def test_knee_at_overbent_threshold_is_borderline(self):
        assert classify_knee_status(140.0) == "borderline"

    def test_borderline_tolerance_respected(self):
        # KNEE_BORDERLINE_TOLERANCE 가 3 이라는 가정 의존성을 명시 (2026-05-25 재조정).
        assert KNEE_BORDERLINE_TOLERANCE == 3

    def test_analyze_knee_flexion_aggregates(
        self, synthetic_running_df, synthetic_strikes
    ):
        result = analyze_knee_flexion(synthetic_running_df, synthetic_strikes)
        assert "avg_angle" in result
        assert "left_avg" in result and "right_avg" in result
        assert sum(result["status_counts"].values()) == 6  # 좌3 + 우3
        assert len(result["per_strike"]) == 6


# ---------------------------------------------------------------------------
# Foot Strike
# ---------------------------------------------------------------------------
class TestFootStrike:
    def test_horizontal_foot_is_zero_degrees(self):
        heel = np.array([0.5, 0.5])
        foot_index = np.array([0.6, 0.5])
        assert calculate_foot_strike_angle(heel, foot_index) == pytest.approx(0.0)

    def test_foot_index_above_heel_is_positive(self):
        # 발끝이 발뒤꿈치보다 화면상 위 → dorsiflexion → 양수 → heel strike 경향.
        heel = np.array([0.5, 0.5])
        foot_index = np.array([0.6, 0.4])  # 위로 0.1
        angle = calculate_foot_strike_angle(heel, foot_index)
        assert angle > 0

    def test_foot_index_below_heel_is_negative(self):
        # 발끝이 발뒤꿈치보다 화면상 아래 → plantarflexion → 음수 → forefoot 경향.
        heel = np.array([0.5, 0.5])
        foot_index = np.array([0.6, 0.6])  # 아래로 0.1
        angle = calculate_foot_strike_angle(heel, foot_index)
        assert angle < 0

    def test_direction_independent_left_vs_right_progression(self):
        # 진행 방향(dx 부호) 이 달라도 같은 발 기울기는 같은 각도여야 한다.
        # 좌→우 진행: 발끝이 오른쪽 + 위.
        a_lr = calculate_foot_strike_angle(
            np.array([0.5, 0.5]), np.array([0.6, 0.4])
        )
        # 우→좌 진행: 발끝이 왼쪽 + 위.
        a_rl = calculate_foot_strike_angle(
            np.array([0.5, 0.5]), np.array([0.4, 0.4])
        )
        assert a_lr == pytest.approx(a_rl)

    def test_foot_at_heel_threshold_is_midfoot(self):
        # 임계값 비교는 strict. HEEL_STRIKE_THRESHOLD 정확히 같으면 midfoot.
        assert classify_foot_strike(float(HEEL_STRIKE_THRESHOLD)) == "mid_foot_strike"

    def test_foot_above_threshold_is_heel(self):
        # 양수 큰 값 → 발끝 위 들림 → heel strike.
        assert classify_foot_strike(10.0) == "heel_strike"

    def test_foot_below_threshold_is_forefoot(self):
        # 음수 큰 값 → 발끝 아래 처짐 → forefoot strike.
        assert classify_foot_strike(-10.0) == "forefoot_strike"

    def test_analyze_foot_strike_synthetic(
        self, synthetic_running_df, synthetic_strikes
    ):
        result = analyze_foot_strike(synthetic_running_df, synthetic_strikes)
        # 합성 데이터는 모두 mid_foot_strike (heel 과 foot_index Y 동일).
        assert result["status_counts"]["midfoot"] == 6
        assert result["status_counts"]["heel"] == 0
        assert result["status_counts"]["forefoot"] == 0


# ---------------------------------------------------------------------------
# Overstriding
# ---------------------------------------------------------------------------
class TestOverstriding:
    def test_distance_absolute_value(self):
        assert calculate_overstride_distance(
            np.array([0.6, 0.8]), np.array([0.5, 0.5])
        ) == pytest.approx(0.1)

    def test_overstride_exactly_at_threshold_is_good(self):
        # 0.15 정확히 → > 가 아니므로 good_stride.
        assert classify_overstride(float(OVERSTRIDE_THRESHOLD)) == "good_stride"

    def test_overstride_above_threshold_is_over(self):
        assert classify_overstride(OVERSTRIDE_THRESHOLD + 1e-6) == "over_stride"

    def test_analyze_overstriding_synthetic(
        self, synthetic_running_df, synthetic_strikes
    ):
        result = analyze_overstriding(synthetic_running_df, synthetic_strikes)
        # 0.02 << 0.15 이므로 모두 good.
        assert result["status_counts"]["over"] == 0
        assert result["status_counts"]["good"] == 6


# ---------------------------------------------------------------------------
# Vertical Oscillation
# ---------------------------------------------------------------------------
class TestVerticalOscillation:
    def test_per_stride_uses_same_foot_pairs(self):
        hip_y = np.linspace(0.4, 0.5, 100)
        strikes = np.array([10, 40, 70])
        strides = calculate_oscillation_per_stride(hip_y, strikes)
        # 3개 착지 → 2개 stride.
        assert len(strides) == 2
        # 모두 단조 증가 시리즈이므로 값 > 0.
        for s in strides:
            assert s["value"] > 0

    def test_classify_threshold(self):
        assert classify_oscillation(VERTICAL_OSC_HIGH_THRESHOLD) == "good_oscillation"
        assert (
            classify_oscillation(VERTICAL_OSC_HIGH_THRESHOLD + 1e-6)
            == "high_oscillation"
        )

    def test_high_oscillation_synthetic(self, synthetic_strikes):
        # 일부러 진폭 큰 hip_y 시리즈를 만들어 high 가 검출되는지.
        n = 100
        rows = [_empty_frame_row(i) for i in range(n)]
        for i, row in enumerate(rows):
            big = 0.4 + 0.1 * math.sin(2 * math.pi * i / 30.0)  # 진폭 0.2
            row["left_hip_y"] = big
            row["right_hip_y"] = big
        df = pd.DataFrame(rows)
        result = analyze_vertical_oscillation(df, synthetic_strikes)
        assert result["status"] == "high"
        assert result["avg_value"] > VERTICAL_OSC_HIGH_THRESHOLD
        # fallback 모드: cm 필드는 None.
        assert result["avg_value_cm"] is None
        assert result["threshold_cm"] is None
        assert result["scale_cm_per_norm"] is None


# ---------------------------------------------------------------------------
# Vertical Oscillation — cm-aware 모드 (Phase 1)
# ---------------------------------------------------------------------------
class TestVerticalOscillationCmAware:
    def _make_df(self, hip_amplitude_norm: float, n: int = 100) -> pd.DataFrame:
        """진폭 hip_amplitude_norm 의 sin hip_y + nose/ankle landmark 포함 df."""
        rows = [_empty_frame_row(i) for i in range(n)]
        for i, row in enumerate(rows):
            v = 0.5 + (hip_amplitude_norm / 2.0) * math.sin(2 * math.pi * i / 30.0)
            row["left_hip_y"] = v
            row["right_hip_y"] = v
            # body_norm_length = 0.5 가 되도록 nose=0.2, ankle=0.7.
            row["nose_x"] = 0.5
            row["nose_y"] = 0.2
            row["nose_z"] = 0.0
            row["nose_visibility"] = 1.0
            row["left_ankle_y"] = 0.7
            row["right_ankle_y"] = 0.7
        return pd.DataFrame(rows)

    def test_cm_mode_above_10cm_is_high(self, synthetic_strikes):
        # height=170cm, body_norm_length=0.5 → scale=340 cm/norm.
        # 진폭 0.04 norm → 13.6cm > 10cm → high.
        df = self._make_df(hip_amplitude_norm=0.04)
        result = analyze_vertical_oscillation(
            df, synthetic_strikes, height_cm=170.0, body_norm_length=0.5
        )
        assert result["status"] == "high"
        assert result["threshold_cm"] == pytest.approx(VO_HIGH_THRESHOLD_CM)
        assert result["scale_cm_per_norm"] == pytest.approx(340.0)
        assert result["avg_value_cm"] > VO_HIGH_THRESHOLD_CM

    def test_cm_mode_below_10cm_is_good(self, synthetic_strikes):
        # 진폭 0.02 norm × 340 = 6.8cm < 10cm → good.
        # 단, 정규화 fallback 기준(0.06)으로는 비교하지 않음 — cm 임계가 우선.
        df = self._make_df(hip_amplitude_norm=0.02)
        result = analyze_vertical_oscillation(
            df, synthetic_strikes, height_cm=170.0, body_norm_length=0.5
        )
        assert result["status"] == "good"
        assert result["avg_value_cm"] < VO_HIGH_THRESHOLD_CM

    def test_cm_mode_taller_runner_more_lenient(self, synthetic_strikes):
        # 같은 정규화 진폭도 신장 차이로 cm 환산이 달라져야 한다.
        # 진폭 0.03 norm:
        #   170cm → 10.2cm (high)
        #   190cm × body_norm_length=0.5 → scale 380 → 11.4cm (high)
        # 신장 입력의 효과를 확인하려면 동일 frame body length 가정에서 cm 값 비교.
        df = self._make_df(hip_amplitude_norm=0.03)
        r_short = analyze_vertical_oscillation(
            df, synthetic_strikes, height_cm=160.0, body_norm_length=0.5
        )
        r_tall = analyze_vertical_oscillation(
            df, synthetic_strikes, height_cm=190.0, body_norm_length=0.5
        )
        # 같은 norm 진폭에서 키 큰 사람의 cm 값이 더 크다.
        assert r_tall["avg_value_cm"] > r_short["avg_value_cm"]
        # height_cm 가 메타데이터에 보존된다.
        assert r_short["height_cm"] == pytest.approx(160.0)
        assert r_tall["height_cm"] == pytest.approx(190.0)

    def test_per_stride_carries_value_cm(self, synthetic_strikes):
        df = self._make_df(hip_amplitude_norm=0.04)
        result = analyze_vertical_oscillation(
            df, synthetic_strikes, height_cm=170.0, body_norm_length=0.5
        )
        assert len(result["per_stride"]) > 0
        for s in result["per_stride"]:
            assert s["value_cm"] is not None
            assert s["value_cm"] == pytest.approx(s["value"] * 340.0)

    def test_fallback_when_height_none(self, synthetic_strikes):
        df = self._make_df(hip_amplitude_norm=0.04)
        result = analyze_vertical_oscillation(
            df, synthetic_strikes, height_cm=None, body_norm_length=0.5
        )
        assert result["avg_value_cm"] is None
        assert result["threshold_cm"] is None
        # 0.04 > 0.06 (norm fallback) 이 아니므로 good.
        assert result["status"] == "good"

    def test_fallback_when_body_norm_length_nan(self, synthetic_strikes):
        # body_norm_length 추정 실패 시 fallback. height 만 있어도 cm 변환 불가.
        df = self._make_df(hip_amplitude_norm=0.07)
        result = analyze_vertical_oscillation(
            df, synthetic_strikes, height_cm=170.0, body_norm_length=float("nan")
        )
        assert result["avg_value_cm"] is None
        # 0.07 > 0.06 → fallback 정규화 임계에서는 high.
        assert result["status"] == "high"

    def test_fallback_when_body_norm_length_zero(self, synthetic_strikes):
        df = self._make_df(hip_amplitude_norm=0.02)
        result = analyze_vertical_oscillation(
            df, synthetic_strikes, height_cm=170.0, body_norm_length=0.0
        )
        # 0 length 도 fallback 처리.
        assert result["scale_cm_per_norm"] is None


# ---------------------------------------------------------------------------
# Body Scale 추정
# ---------------------------------------------------------------------------
class TestBodyNormLength:
    def test_basic_median(self):
        # nose y=0.1, ankle y=0.9 → length 0.8 across all frames.
        rows = []
        for i in range(50):
            row = _empty_frame_row(i)
            row["nose_x"] = 0.5
            row["nose_y"] = 0.1
            row["nose_z"] = 0.0
            row["nose_visibility"] = 1.0
            row["left_ankle_y"] = 0.9
            row["right_ankle_y"] = 0.9
            rows.append(row)
        df = pd.DataFrame(rows)
        assert compute_body_norm_length(df) == pytest.approx(0.8)

    def test_uses_lower_ankle_robust_to_one_side_nan(self):
        # 한쪽 ankle 이 NaN 이어도 다른쪽으로 통과 (fmax).
        rows = []
        for i in range(20):
            row = _empty_frame_row(i)
            row["nose_x"] = 0.5
            row["nose_y"] = 0.1
            row["nose_z"] = 0.0
            row["nose_visibility"] = 1.0
            row["left_ankle_y"] = float("nan")
            row["right_ankle_y"] = 0.85
            rows.append(row)
        df = pd.DataFrame(rows)
        assert compute_body_norm_length(df) == pytest.approx(0.75)

    def test_returns_nan_when_no_valid_frame(self):
        rows = []
        for i in range(10):
            row = _empty_frame_row(i)
            row["nose_x"] = 0.5
            row["nose_y"] = float("nan")
            row["nose_z"] = 0.0
            row["nose_visibility"] = 0.0
            row["left_ankle_y"] = float("nan")
            row["right_ankle_y"] = float("nan")
            rows.append(row)
        df = pd.DataFrame(rows)
        assert math.isnan(compute_body_norm_length(df))

    def test_missing_columns_returns_nan(self):
        # nose 컬럼 자체가 없는 df 도 NaN 반환 (deprecated/legacy 케이스).
        rows = [_empty_frame_row(i) for i in range(5)]
        df = pd.DataFrame(rows)
        assert "nose_y" not in df.columns
        assert math.isnan(compute_body_norm_length(df))


# ---------------------------------------------------------------------------
# Asymmetry
# ---------------------------------------------------------------------------
class TestAsymmetry:
    def test_ratio_basic(self):
        # L=100, R=120 → |20|/120 ≈ 0.1667
        assert calculate_asymmetry_ratio(100, 120) == pytest.approx(20 / 120)

    def test_ratio_nan_when_both_zero(self):
        assert math.isnan(calculate_asymmetry_ratio(0.0, 0.0))

    def test_ratio_nan_propagates(self):
        assert math.isnan(calculate_asymmetry_ratio(float("nan"), 1.0))

    def test_strike_count_alone_does_not_warn(self):
        # 큰 strike 비대칭(50%)이라도 knee/osc 정상이면 워닝 안 뜸 — 트리거 격하 정책.
        # pace7/630 false positive 해결 케이스.
        strikes = {"left": np.arange(10), "right": np.arange(5)}  # ratio 50%
        knee = {"left_avg": 150.0, "right_avg": 150.0}
        vosc = {"left_avg": 0.04, "right_avg": 0.04}
        result = analyze_asymmetry(strikes, knee, vosc)
        assert result["strike_count_ratio"] == pytest.approx(0.5)
        assert result["is_warning"] is False

    def test_knee_asymmetry_triggers_warning(self):
        strikes = {"left": np.arange(20), "right": np.arange(20)}
        knee = {"left_avg": 150.0, "right_avg": 170.0}  # ratio≈11.8%
        vosc = {"left_avg": 0.04, "right_avg": 0.04}
        result = analyze_asymmetry(strikes, knee, vosc)
        assert result["is_warning"] is True

    def test_oscillation_asymmetry_triggers_warning(self):
        strikes = {"left": np.arange(20), "right": np.arange(20)}
        knee = {"left_avg": 150.0, "right_avg": 150.0}
        vosc = {"left_avg": 0.04, "right_avg": 0.05}  # ratio = 20%
        result = analyze_asymmetry(strikes, knee, vosc)
        assert result["is_warning"] is True

    def test_all_symmetric_no_warn(self):
        strikes = {"left": np.arange(10), "right": np.arange(10)}
        knee = {"left_avg": 150.0, "right_avg": 152.0}
        vosc = {"left_avg": 0.04, "right_avg": 0.041}
        result = analyze_asymmetry(strikes, knee, vosc)
        assert result["is_warning"] is False
        assert ASYMMETRY_WARNING_THRESHOLD == 0.1

    def test_visibility_diff_invalidates_strike_ratio(self):
        # 좌/우 발 visibility 차이가 임계 초과면 strike_count_ratio → NaN.
        strikes = {"left": np.arange(10), "right": np.arange(5)}
        knee = {"left_avg": 150.0, "right_avg": 150.0}
        vosc = {"left_avg": 0.04, "right_avg": 0.04}
        result = analyze_asymmetry(
            strikes, knee, vosc,
            foot_visibility={"left": 0.85, "right": 0.70},  # diff=0.15 > 0.10
        )
        assert math.isnan(result["strike_count_ratio"])
        # 트리거에는 영향 없음 (이미 strike 단독 트리거 비활성).
        assert result["is_warning"] is False

    def test_visibility_balanced_keeps_strike_ratio(self):
        # 좌/우 visibility 차이 작으면 strike_count_ratio 보존.
        strikes = {"left": np.arange(10), "right": np.arange(5)}
        knee = {"left_avg": 150.0, "right_avg": 150.0}
        vosc = {"left_avg": 0.04, "right_avg": 0.04}
        result = analyze_asymmetry(
            strikes, knee, vosc,
            foot_visibility={"left": 0.85, "right": 0.82},  # diff=0.03
        )
        assert result["strike_count_ratio"] == pytest.approx(0.5)

    def test_visibility_none_keeps_strike_ratio(self):
        # 하위 호환: foot_visibility 안 넘기면 strike_ratio 그대로.
        strikes = {"left": np.arange(10), "right": np.arange(5)}
        knee = {"left_avg": 150.0, "right_avg": 150.0}
        vosc = {"left_avg": 0.04, "right_avg": 0.04}
        result = analyze_asymmetry(strikes, knee, vosc)
        assert result["strike_count_ratio"] == pytest.approx(0.5)

    def test_foot_vis_threshold_constant_pinned(self):
        # 설계 가정 (0.10) 이 변경되면 위 케이스 임계가 흔들리므로 핀.
        assert ASYMMETRY_FOOT_VIS_DIFF_THRESHOLD == 0.10


# ---------------------------------------------------------------------------
# Pydantic 모델 직렬화
# ---------------------------------------------------------------------------
class TestAnalysisResultModel:
    def test_serialization_roundtrip(
        self, synthetic_running_df, synthetic_strikes
    ):
        from models.analysis_result import AnalysisResult, DangerTimestamp

        knee = analyze_knee_flexion(synthetic_running_df, synthetic_strikes)
        foot = analyze_foot_strike(synthetic_running_df, synthetic_strikes)
        over = analyze_overstriding(synthetic_running_df, synthetic_strikes)
        vosc = analyze_vertical_oscillation(
            synthetic_running_df, synthetic_strikes
        )
        asym = analyze_asymmetry(synthetic_strikes, knee, vosc)

        result = AnalysisResult(
            analysis_id="test-001",
            summary={"total_strikes": 6},
            metrics={
                "knee_flexion": knee,
                "foot_strike": foot,
                "overstriding": over,
                "vertical_oscillation": vosc,
            },
            asymmetry=asym,
            danger_timestamps=[DangerTimestamp(time_sec=1.23, type="heel_strike")],
        )
        payload = result.model_dump_json()
        assert "knee_flexion" in payload
        assert "heel_strike" in payload
