"""
분석 결과 통합 Pydantic 스키마.

이 모델은 API 응답과 Step 3(렌더링·코칭)의 입력으로 직접 사용된다.
metrics 딕셔너리의 키는 지표별로 다르므로 dict 로 유연하게 보관한다.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class MetricResult(BaseModel):
    """단일 지표의 공통 형태 (실제 저장은 dict 로 하므로 참고용 스키마)."""

    avg_value: float | None = None
    status_counts: dict[str, int]
    per_event: list[dict] = Field(default_factory=list)


class DangerTimestamp(BaseModel):
    """타임라인에 표시할 🔴 위험 이벤트."""

    time_sec: float
    type: Literal["heel_strike", "stiff_knee", "over_stride", "high_oscillation"]
    color: Literal["red"] = "red"


class QualityWarning(BaseModel):
    """입력 영상 품질 경고 (PRD-8).

    code 는 로깅/추적/i18n 키용, message_ko 는 사용자 표시용.
    """

    code: str
    message_ko: str


class AnalysisResult(BaseModel):
    """전체 분석 결과 최상위 모델."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    analysis_id: str
    summary: dict
    metrics: dict  # {knee_flexion, foot_strike, overstriding, vertical_oscillation}
    asymmetry: dict
    danger_timestamps: list[DangerTimestamp] = Field(default_factory=list)

    # PRD-8: 입력 영상 품질 평가.
    confidence: Literal["high", "medium", "low"] = "high"
    warnings: list[QualityWarning] = Field(default_factory=list)


__all__ = ["MetricResult", "DangerTimestamp", "QualityWarning", "AnalysisResult"]
