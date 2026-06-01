"""
PRD-3 csv_reporter 단위 테스트.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from analyzer.csv_reporter import generate_csv_report
from models.analysis_result import AnalysisResult


def _df(n: int = 10, fps: float = 30.0) -> pd.DataFrame:
    rows = [
        {
            "frame_idx": i,
            "timestamp_sec": i / fps,
            "left_hip_y": 0.55,
            "right_hip_y": 0.55,
        }
        for i in range(n)
    ]
    df = pd.DataFrame(rows)
    df.attrs["fps"] = fps
    return df


def _result_with_strike(frame: int = 5) -> AnalysisResult:
    return AnalysisResult(
        analysis_id="csv-test",
        summary={
            "total_frames": 10,
            "duration_sec": 10 / 30.0,
            "fps": 30.0,
            "total_strikes": 1,
            "left_strikes": 1,
            "right_strikes": 0,
            "danger_count": 1,
            "cadence_spm": 0.0,
        },
        metrics={
            "knee_flexion": {
                "avg_angle": 165.0,
                "left_avg": 165.0,
                "right_avg": float("nan"),
                "status_counts": {"stiff": 1, "good": 0, "over_bent": 0, "borderline": 0},
                "per_strike": [
                    {"frame": frame, "angle": 165.0, "status": "stiff_knee", "foot": "left"}
                ],
            },
            "foot_strike": {
                "status_counts": {"heel": 1, "midfoot": 0, "forefoot": 0},
                "per_strike": [
                    {"frame": frame, "angle": -10.0, "status": "heel_strike", "foot": "left"}
                ],
            },
            "overstriding": {
                "avg_distance": 0.2,
                "status_counts": {"good": 0, "over": 1},
                "per_strike": [
                    {"frame": frame, "distance": 0.2, "status": "over_stride", "foot": "left"}
                ],
            },
            "vertical_oscillation": {
                "avg_value": 0.05,
                "left_avg": 0.05,
                "right_avg": float("nan"),
                "status": "good",
                "per_stride": [],
            },
        },
        asymmetry={
            "strike_count_ratio": 1.0,
            "knee_angle_ratio": 0.0,
            "oscillation_ratio": 0.0,
            "is_warning": True,
        },
        confidence="high",
    )


def test_csv_creates_file(tmp_path: Path):
    out = tmp_path / "report.csv"
    generate_csv_report(str(out), _df(), _result_with_strike())
    assert out.exists()


def test_csv_columns_and_row_count(tmp_path: Path):
    out = tmp_path / "report.csv"
    generate_csv_report(str(out), _df(n=10), _result_with_strike())
    df = pd.read_csv(out)
    assert len(df) == 10
    for col in (
        "frame_idx",
        "time_sec",
        "foot",
        "knee_angle",
        "knee_status",
        "foot_strike_angle",
        "foot_strike_status",
        "overstride_distance",
        "overstride_status",
        "hip_y",
        "is_foot_strike",
    ):
        assert col in df.columns


def test_csv_strike_frame_populated(tmp_path: Path):
    out = tmp_path / "report.csv"
    generate_csv_report(str(out), _df(n=10), _result_with_strike(frame=5))
    df = pd.read_csv(out)
    strike_row = df[df["frame_idx"] == 5].iloc[0]
    assert strike_row["foot"] == "left"
    assert strike_row["knee_status"] == "stiff_knee"
    assert strike_row["foot_strike_status"] == "heel_strike"
    assert strike_row["overstride_status"] == "over_stride"
    assert bool(strike_row["is_foot_strike"]) is True

    non_strike = df[df["frame_idx"] == 0].iloc[0]
    assert non_strike["foot"] == "" or pd.isna(non_strike["foot"])
    assert bool(non_strike["is_foot_strike"]) is False
