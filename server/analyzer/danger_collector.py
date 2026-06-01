"""
🔴 위험 타임스탬프 수집기 (PRD-3).

`AnalysisResult.metrics` 에서 위험 상태(stiff_knee / heel_strike / over_stride /
high_oscillation) 만 추출해 시간순 DangerTimestamp 리스트로 반환한다.

`analyzer.__init__._collect_danger_timestamps` 와 동일 로직을 외부 모듈로 분리한
것. PRD-3 산출물(렌더링 영상, CSV 등)이 동일한 위험 타임라인을 공유하기 위함.
"""
from __future__ import annotations

import logging

from config import TARGET_FPS
from models.analysis_result import AnalysisResult, DangerTimestamp

logger = logging.getLogger(__name__)


def _frame_to_sec(frame_idx: int, fps: float) -> float:
    if fps <= 0:
        fps = TARGET_FPS
    return round(frame_idx / fps, 3)


def collect_danger_timestamps(
    result: AnalysisResult,
    fps: float = TARGET_FPS,
) -> list[DangerTimestamp]:
    """
    AnalysisResult 의 모든 지표 per_strike/per_stride 에서 🔴 만 추출해
    DangerTimestamp 리스트로 반환. 시간 오름차순.
    """
    danger: list[DangerTimestamp] = []
    metrics = result.metrics

    for entry in metrics.get("knee_flexion", {}).get("per_strike", []):
        if entry.get("status") == "stiff_knee":
            danger.append(
                DangerTimestamp(
                    time_sec=_frame_to_sec(entry["frame"], fps),
                    type="stiff_knee",
                )
            )

    for entry in metrics.get("foot_strike", {}).get("per_strike", []):
        if entry.get("status") == "heel_strike":
            danger.append(
                DangerTimestamp(
                    time_sec=_frame_to_sec(entry["frame"], fps),
                    type="heel_strike",
                )
            )

    for entry in metrics.get("overstriding", {}).get("per_strike", []):
        if entry.get("status") == "over_stride":
            danger.append(
                DangerTimestamp(
                    time_sec=_frame_to_sec(entry["frame"], fps),
                    type="over_stride",
                )
            )

    for entry in metrics.get("vertical_oscillation", {}).get("per_stride", []):
        if entry.get("status") == "high_oscillation":
            danger.append(
                DangerTimestamp(
                    time_sec=_frame_to_sec(entry["start_frame"], fps),
                    type="high_oscillation",
                )
            )

    danger.sort(key=lambda d: d.time_sec)
    logger.info("collected danger timestamps: %d", len(danger))
    return danger


__all__ = ["collect_danger_timestamps"]
