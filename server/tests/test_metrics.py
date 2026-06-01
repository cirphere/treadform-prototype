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
from analyzer.metrics.posture import (
    analyze_arm_position,
    analyze_head_position,
    analyze_landing_tibia,
    analyze_posture_metrics,
    analyze_torso_posture,
    classify_arm_angle,
    classify_head_position,
    classify_tibia,
    classify_torso_lean,
)
from analyzer.metrics.vertical_osc import (
    analyze_vertical_oscillation,
    calculate_oscillation_per_stride,
    classify_oscillation,
)
from config import (
    ASYMMETRY_FOOT_VIS_DIFF_THRESHOLD,
    ASYMMETRY_WARNING_THRESHOLD,
    HEEL_STRIKE_THRESHOLD,
    KNEE_BORDERLINE_TOLERANCE,
    KNEE_STIFF_THRESHOLD,
    OVERSTRIDE_THRESHOLD,
    VERTICAL_OSC_HIGH_THRESHOLD,
)


# ---------------------------------------------------------------------------
# 합성 데이터 픽스처
# ---------------------------------------------------------------------------
LANDMARKS = [
    "left_hip",
    "right_hip",
    "nose",
    "left_ear",
    "right_ear",
    "left_shoulder",
    "right_shoulder",
    "left_elbow",
    "right_elbow",
    "left_wrist",
    "right_wrist",
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
    # 측면 러닝 기본 상체 포즈: 약 10° 몸통 기울기, 자연스러운 팔꿈치 각도,
    # 머리는 어깨 위에 가깝게 정렬.
    row["left_shoulder_x"] = 0.54
    row["right_shoulder_x"] = 0.54
    row["left_shoulder_y"] = 0.20
    row["right_shoulder_y"] = 0.20
    row["left_elbow_x"] = 0.60
    row["right_elbow_x"] = 0.60
    row["left_elbow_y"] = 0.32
    row["right_elbow_y"] = 0.32
    row["left_wrist_x"] = 0.48
    row["right_wrist_x"] = 0.48
    row["left_wrist_y"] = 0.38
    row["right_wrist_y"] = 0.38
    row["nose_x"] = 0.56
    row["nose_y"] = 0.15
    row["left_ear_x"] = 0.55
    row["right_ear_x"] = 0.55
    row["left_ear_y"] = 0.16
    row["right_ear_y"] = 0.16
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
        # 정확히 160° → ±5° 범위 안 → borderline.
        assert classify_knee_status(float(KNEE_STIFF_THRESHOLD)) == "borderline"

    def test_knee_at_165_is_stiff(self):
        # 160 + 5 초과 영역 → stiff.
        assert classify_knee_status(165.0 + 0.01) == "stiff_knee"

    def test_knee_at_150_is_good(self):
        assert classify_knee_status(150.0) == "good_flexion"

    def test_knee_at_130_is_over_bent(self):
        # 140 - 5 미만 영역 → over_bent.
        assert classify_knee_status(130.0) == "over_bent"

    def test_knee_at_overbent_threshold_is_borderline(self):
        assert classify_knee_status(140.0) == "borderline"

    def test_borderline_tolerance_respected(self):
        # KNEE_BORDERLINE_TOLERANCE 가 5 라는 가정 의존성을 명시.
        assert KNEE_BORDERLINE_TOLERANCE == 5

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


# ---------------------------------------------------------------------------
# Posture / Landing v2
# ---------------------------------------------------------------------------
class TestPostureMetrics:
    def test_tibia_threshold(self):
        assert classify_tibia(5.0) == "good_tibia"
        assert classify_tibia(20.0) == "overreach_tibia"

    def test_analyze_landing_tibia_synthetic(
        self, synthetic_running_df, synthetic_strikes
    ):
        result = analyze_landing_tibia(synthetic_running_df, synthetic_strikes)
        assert len(result["per_strike"]) == 6
        assert result["status_counts"]["good"] == 6
        assert result["avg_angle"] < 12.0

    def test_torso_posture_synthetic(self, synthetic_running_df):
        result = analyze_torso_posture(synthetic_running_df)
        assert result["status"] == "neutral_torso"
        assert 3.0 <= result["avg_angle"] <= 25.0
        assert classify_torso_lean(0.0) == "too_upright"
        assert classify_torso_lean(30.0) == "excessive_lean"

    def test_arm_position_synthetic(self, synthetic_running_df):
        result = analyze_arm_position(synthetic_running_df)
        assert result["status"] == "good_arm_swing"
        assert classify_arm_angle(50.0) == "too_tight"
        assert classify_arm_angle(130.0) == "too_open"

    def test_head_position_synthetic(self, synthetic_running_df):
        result = analyze_head_position(synthetic_running_df)
        assert result["status"] == "aligned_head"
        assert classify_head_position(0.3) == "forward_head"

    def test_analyze_posture_metrics_contains_all_keys(
        self, synthetic_running_df, synthetic_strikes
    ):
        result = analyze_posture_metrics(synthetic_running_df, synthetic_strikes)
        assert set(result.keys()) == {
            "landing_tibia",
            "torso_posture",
            "arm_position",
            "head_position",
        }


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
        posture = analyze_posture_metrics(synthetic_running_df, synthetic_strikes)
        asym = analyze_asymmetry(synthetic_strikes, knee, vosc)

        result = AnalysisResult(
            analysis_id="test-001",
            summary={"total_strikes": 6},
            metrics={
                "knee_flexion": knee,
                "foot_strike": foot,
                "overstriding": over,
                "vertical_oscillation": vosc,
                **posture,
            },
            asymmetry=asym,
            danger_timestamps=[DangerTimestamp(time_sec=1.23, type="heel_strike")],
        )
        payload = result.model_dump_json()
        assert "knee_flexion" in payload
        assert "torso_posture" in payload
        assert "heel_strike" in payload
