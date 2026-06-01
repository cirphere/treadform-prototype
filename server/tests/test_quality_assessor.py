"""
quality_assessor 단위 테스트 (PRD-8 소프트 경고).

각 경고 코드별 트리거 케이스 + 신뢰도 등급 경계값 확인.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from analyzer.quality_assessor import (
    QualityReport,
    assess,
)
from config import (
    MIN_DETECTED_FRAME_RATIO,
    WARN_FPS_FOR_HIGH_CADENCE,
    WARN_HIGH_CADENCE_SPM,
    WARN_LOW_AVG_VISIBILITY,
    WARN_SIDE_ANGLE_DEVIATION,
)


def _good_frame(idx: int) -> dict:
    """모든 경고를 안 띄우는 정상 측면 프레임 1개."""
    # 측면이므로 양 어깨 x 가 거의 같음. 토르소는 ~0.3.
    row = {
        "frame_idx": idx,
        "timestamp_sec": idx / 30.0,
        "left_shoulder_x": 0.50,
        "right_shoulder_x": 0.51,
        "left_shoulder_y": 0.30,
        "left_hip_x": 0.50,
        "left_hip_y": 0.60,
        "left_hip_visibility": 0.9,
        "right_hip_x": 0.50,
        "right_hip_y": 0.60,
        "right_hip_visibility": 0.9,
        "left_knee_visibility": 0.9,
        "right_knee_visibility": 0.9,
        "left_ankle_visibility": 0.9,
        "right_ankle_visibility": 0.9,
    }
    return row


def _good_df(n: int = 100) -> pd.DataFrame:
    return pd.DataFrame([_good_frame(i) for i in range(n)])


class TestHighConfidence:
    def test_no_warnings_yields_high(self):
        df = _good_df()
        report = assess(df, fps=60.0, cadence_spm=170.0)
        assert isinstance(report, QualityReport)
        assert report.confidence == "high"
        assert report.warnings == []


class TestLowDetectionRatio:
    def test_low_detection_ratio_warns(self):
        df = _good_df(100)
        # 50% 프레임의 left_hip_x 를 NaN 으로 → ratio 0.5 < 0.70
        df.loc[:49, "left_hip_x"] = np.nan
        report = assess(df, fps=60.0, cadence_spm=170.0)
        codes = [w["code"] for w in report.warnings]
        assert "LOW_DETECTION_RATIO" in codes
        assert report.metrics["detected_frame_ratio"] == pytest.approx(0.5)

    def test_ratio_above_threshold_no_warn(self):
        df = _good_df(100)
        # 71% 검출 → 통과.
        df.loc[:28, "left_hip_x"] = np.nan
        report = assess(df, fps=60.0, cadence_spm=170.0)
        codes = [w["code"] for w in report.warnings]
        assert "LOW_DETECTION_RATIO" not in codes


class TestLowVisibility:
    def test_low_visibility_warns(self):
        df = _good_df(50)
        for c in df.columns:
            if c.endswith("_visibility"):
                df[c] = 0.4  # 0.40 < 0.60
        report = assess(df, fps=60.0, cadence_spm=170.0)
        codes = [w["code"] for w in report.warnings]
        assert "LOW_VISIBILITY" in codes

    def test_visibility_at_threshold_no_warn(self):
        df = _good_df(50)
        for c in df.columns:
            if c.endswith("_visibility"):
                df[c] = WARN_LOW_AVG_VISIBILITY + 0.01
        report = assess(df, fps=60.0, cadence_spm=170.0)
        codes = [w["code"] for w in report.warnings]
        assert "LOW_VISIBILITY" not in codes


class TestHighCadenceLowFps:
    def test_fast_pace_low_fps_warns(self):
        df = _good_df(50)
        report = assess(df, fps=30.0, cadence_spm=200.0)
        codes = [w["code"] for w in report.warnings]
        assert "HIGH_CADENCE_LOW_FPS" in codes

    def test_fast_pace_high_fps_no_warn(self):
        df = _good_df(50)
        report = assess(df, fps=60.0, cadence_spm=200.0)
        codes = [w["code"] for w in report.warnings]
        assert "HIGH_CADENCE_LOW_FPS" not in codes

    def test_slow_pace_low_fps_no_warn(self):
        df = _good_df(50)
        report = assess(df, fps=30.0, cadence_spm=170.0)
        codes = [w["code"] for w in report.warnings]
        assert "HIGH_CADENCE_LOW_FPS" not in codes


class TestNotSideView:
    def test_frontal_view_warns(self):
        # 정면: 양 어깨 x 차이가 크고 (0.3), 토르소 길이 0.3 → ratio 1.0 > 0.25
        df = _good_df(50)
        df["left_shoulder_x"] = 0.35
        df["right_shoulder_x"] = 0.65
        report = assess(df, fps=60.0, cadence_spm=170.0)
        codes = [w["code"] for w in report.warnings]
        assert "NOT_SIDE_VIEW" in codes

    def test_side_view_no_warn(self):
        df = _good_df(50)
        # 기본값이 측면. side_dev ≈ 0.03 < 0.25
        report = assess(df, fps=60.0, cadence_spm=170.0)
        codes = [w["code"] for w in report.warnings]
        assert "NOT_SIDE_VIEW" not in codes


class TestConfidenceGrading:
    def test_one_warning_yields_medium(self):
        df = _good_df(50)
        report = assess(df, fps=30.0, cadence_spm=200.0)  # 1개만 트리거
        assert len(report.warnings) == 1
        assert report.confidence == "medium"

    def test_two_warnings_still_medium(self):
        df = _good_df(50)
        # 빠른 페이스 + 정면 촬영.
        df["left_shoulder_x"] = 0.35
        df["right_shoulder_x"] = 0.65
        report = assess(df, fps=30.0, cadence_spm=200.0)
        assert len(report.warnings) == 2
        assert report.confidence == "medium"

    def test_three_or_more_yields_low(self):
        df = _good_df(100)
        # 검출률 낮음 + visibility 낮음 + 빠른 페이스 = 3개
        df.loc[:49, "left_hip_x"] = np.nan
        for c in df.columns:
            if c.endswith("_visibility"):
                df[c] = 0.3
        report = assess(df, fps=30.0, cadence_spm=200.0)
        assert len(report.warnings) >= 3
        assert report.confidence == "low"


class TestMetricsExposed:
    def test_metrics_dict_populated(self):
        df = _good_df(50)
        report = assess(df, fps=30.0, cadence_spm=180.0)
        assert "detected_frame_ratio" in report.metrics
        assert "avg_visibility" in report.metrics
        assert "cadence_spm" in report.metrics
        assert "fps" in report.metrics
        assert "side_angle_deviation" in report.metrics
        assert report.metrics["cadence_spm"] == 180.0
        assert report.metrics["fps"] == 30.0


class TestEdgeCases:
    def test_empty_dataframe(self):
        df = pd.DataFrame()
        report = assess(df, fps=30.0, cadence_spm=0.0)
        # 빈 DF: 검출률 0 → LOW_DETECTION_RATIO 1개. visibility 컬럼 없음 → 평균 0 → LOW_VISIBILITY.
        assert report.confidence in {"medium", "low"}

    def test_missing_shoulder_columns(self):
        # 어깨 컬럼이 없으면 side_dev = 0 → NOT_SIDE_VIEW 안 뜸.
        df = pd.DataFrame([
            {
                "frame_idx": i,
                "left_hip_x": 0.5,
                "left_hip_visibility": 0.9,
            }
            for i in range(20)
        ])
        report = assess(df, fps=60.0, cadence_spm=170.0)
        codes = [w["code"] for w in report.warnings]
        assert "NOT_SIDE_VIEW" not in codes
