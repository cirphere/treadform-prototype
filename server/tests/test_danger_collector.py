"""
PRD-3 danger_collector 단위 테스트.
"""
from __future__ import annotations

from analyzer.danger_collector import collect_danger_timestamps
from models.analysis_result import AnalysisResult


def _result() -> AnalysisResult:
    return AnalysisResult(
        analysis_id="danger-test",
        summary={},
        metrics={
            "knee_flexion": {
                "per_strike": [
                    {"frame": 30, "angle": 165.0, "status": "stiff_knee", "foot": "left"},
                    {"frame": 60, "angle": 150.0, "status": "good_flexion", "foot": "right"},
                ]
            },
            "foot_strike": {
                "per_strike": [
                    {"frame": 30, "angle": -10.0, "status": "heel_strike", "foot": "left"},
                ]
            },
            "overstriding": {
                "per_strike": [
                    {"frame": 90, "distance": 0.2, "status": "over_stride", "foot": "right"},
                ]
            },
            "vertical_oscillation": {
                "per_stride": [
                    {"start_frame": 0, "end_frame": 60, "value": 0.1,
                     "status": "high_oscillation", "foot": "left"},
                ]
            },
        },
        asymmetry={},
        confidence="high",
    )


def test_collect_returns_only_danger():
    danger = collect_danger_timestamps(_result(), fps=30.0)
    types = [d.type for d in danger]
    # stiff_knee + heel_strike + high_oscillation + over_stride 모두 포함.
    assert sorted(types) == sorted(
        ["stiff_knee", "heel_strike", "over_stride", "high_oscillation"]
    )


def test_collect_sorted_by_time():
    danger = collect_danger_timestamps(_result(), fps=30.0)
    times = [d.time_sec for d in danger]
    assert times == sorted(times)


def test_frame_to_sec_conversion():
    danger = collect_danger_timestamps(_result(), fps=30.0)
    heel = next(d for d in danger if d.type == "heel_strike")
    assert heel.time_sec == 1.0  # frame 30 / 30 fps


def test_collect_empty_when_no_danger():
    empty = AnalysisResult(
        analysis_id="empty",
        summary={},
        metrics={
            "knee_flexion": {"per_strike": []},
            "foot_strike": {"per_strike": []},
            "overstriding": {"per_strike": []},
            "vertical_oscillation": {"per_stride": []},
        },
        asymmetry={},
        confidence="high",
    )
    assert collect_danger_timestamps(empty, fps=30.0) == []
