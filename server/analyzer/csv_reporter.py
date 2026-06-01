"""
프레임별 모든 지표를 CSV 로 저장 (PRD-3).

트레이너용 객관 자료. 컬럼 구조:
    frame_idx, time_sec, foot,
    knee_angle, knee_status,
    foot_strike_angle, foot_strike_status,
    overstride_distance, overstride_status,
    hip_y, is_foot_strike

`foot` 컬럼은 해당 프레임에 착지가 있었던 발 ("left" | "right") 이며 착지가
없는 프레임은 빈 문자열 ("") 로 둔다.
"""
from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

from config import TARGET_FPS
from models.analysis_result import AnalysisResult

logger = logging.getLogger(__name__)


_CSV_COLUMNS = [
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
]


def _strike_lookup(metrics: dict) -> dict[int, dict]:
    """frame_idx → 해당 프레임의 (knee/foot_strike/overstriding) per_strike 모음."""
    lookup: dict[int, dict] = {}

    def _put(metric_name: str, sub_key: str):
        for entry in metrics.get(metric_name, {}).get("per_strike", []):
            f = int(entry["frame"])
            slot = lookup.setdefault(f, {"foot": entry.get("foot", "")})
            slot[sub_key] = entry

    _put("knee_flexion", "knee")
    _put("foot_strike", "foot_strike")
    _put("overstriding", "overstride")
    return lookup


def generate_csv_report(
    output_csv_path: str,
    keypoints_df: pd.DataFrame,
    analysis_result: AnalysisResult,
) -> str:
    """
    프레임별 지표 CSV 저장.

    Args:
        output_csv_path: 출력 csv 절대 경로.
        keypoints_df: 전처리된 keypoints DataFrame (frame_idx, timestamp_sec 포함).
        analysis_result: 분석 결과.

    Returns:
        저장된 절대 경로.
    """
    out = Path(output_csv_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    fps = float(keypoints_df.attrs.get("fps", TARGET_FPS))
    lookup = _strike_lookup(analysis_result.metrics)

    rows: list[dict] = []
    for _, kp_row in keypoints_df.iterrows():
        frame_idx = int(kp_row["frame_idx"])
        time_sec = float(kp_row.get("timestamp_sec", frame_idx / fps))

        # hip_y: 좌/우 평균 (둘 다 NaN 이면 NaN).
        left_hip_y = kp_row.get("left_hip_y")
        right_hip_y = kp_row.get("right_hip_y")
        if pd.notna(left_hip_y) and pd.notna(right_hip_y):
            hip_y = (float(left_hip_y) + float(right_hip_y)) / 2.0
        elif pd.notna(left_hip_y):
            hip_y = float(left_hip_y)
        elif pd.notna(right_hip_y):
            hip_y = float(right_hip_y)
        else:
            hip_y = float("nan")

        slot = lookup.get(frame_idx)
        if slot is None:
            rows.append({
                "frame_idx": frame_idx,
                "time_sec": round(time_sec, 4),
                "foot": "",
                "knee_angle": float("nan"),
                "knee_status": "",
                "foot_strike_angle": float("nan"),
                "foot_strike_status": "",
                "overstride_distance": float("nan"),
                "overstride_status": "",
                "hip_y": hip_y,
                "is_foot_strike": False,
            })
            continue

        knee = slot.get("knee", {})
        fs = slot.get("foot_strike", {})
        over = slot.get("overstride", {})
        rows.append({
            "frame_idx": frame_idx,
            "time_sec": round(time_sec, 4),
            "foot": slot.get("foot", ""),
            "knee_angle": knee.get("angle", float("nan")),
            "knee_status": knee.get("status", ""),
            "foot_strike_angle": fs.get("angle", float("nan")),
            "foot_strike_status": fs.get("status", ""),
            "overstride_distance": over.get("distance", float("nan")),
            "overstride_status": over.get("status", ""),
            "hip_y": hip_y,
            "is_foot_strike": True,
        })

    df = pd.DataFrame(rows, columns=_CSV_COLUMNS)
    df.to_csv(out, index=False, encoding="utf-8-sig")
    logger.info("csv report saved: %s (%d rows)", out, len(df))
    return str(out.resolve())


__all__ = ["generate_csv_report"]
