"""
영상 품질 경고 산출 (PRD-8 소프트 경고).

video_validator 가 하드 요건을 통과시킨 영상에 대해서만 호출된다.
분석을 막지는 않고, AnalysisResult 에 confidence + warnings 로 첨부된다.

경고 코드:
    LOW_DETECTION_RATIO       - 사람 검출 프레임 < MIN_DETECTED_FRAME_RATIO
    LOW_VISIBILITY            - 평균 visibility < WARN_LOW_AVG_VISIBILITY
    HIGH_CADENCE_LOW_FPS      - cadence ≥ WARN_HIGH_CADENCE_SPM AND fps < WARN_FPS_FOR_HIGH_CADENCE
    NOT_SIDE_VIEW             - 양 어깨 x 거리 / 토르소 길이 > WARN_SIDE_ANGLE_DEVIATION
    SIDE_VIEW_ASYM_CAUTION    - 측면 촬영에서 비대칭 워닝이 떴을 때 해석 caveat
                                (assess() 이후 apply_asymmetry_caveats() 로 첨부)
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from config import (
    CONFIDENCE_HIGH_MAX_WARNINGS,
    CONFIDENCE_MEDIUM_MAX_WARNINGS,
    MIN_DETECTED_FRAME_RATIO,
    WARN_FPS_FOR_HIGH_CADENCE,
    WARN_HIGH_CADENCE_SPM,
    WARN_LOW_AVG_VISIBILITY,
    WARN_SIDE_ANGLE_DEVIATION,
)

logger = logging.getLogger(__name__)


@dataclass
class QualityReport:
    """품질 평가 결과."""

    confidence: str                                       # "high" | "medium" | "low"
    warnings: list[dict] = field(default_factory=list)    # [{code, message_ko}, ...]
    metrics: dict = field(default_factory=dict)           # 디버그용 측정값


def _detected_frame_ratio(df: pd.DataFrame) -> float:
    """left_hip_x 가 NaN 이 아닌 프레임 비율 (raw 기준).

    raw_df 는 pose_extractor 가 visibility masking 전에 만든 DataFrame 이므로
    NaN 은 사람이 아예 검출되지 않은 프레임을 의미한다.
    """
    if "left_hip_x" not in df.columns or len(df) == 0:
        return 0.0
    return float(df["left_hip_x"].notna().mean())


def _avg_visibility(df: pd.DataFrame) -> float:
    """모든 _visibility 컬럼의 전역 평균. 컬럼/데이터 없으면 0."""
    cols = [c for c in df.columns if c.endswith("_visibility")]
    if not cols or len(df) == 0:
        return 0.0
    return float(df[cols].mean(skipna=True).mean())


def _side_angle_deviation(df: pd.DataFrame) -> float:
    """양 어깨 x 거리 / 토르소 세로 길이 (median).

    측면 촬영 ≈ 0 (양 어깨가 깊이 방향으로 겹침)
    정면 촬영 ≈ 1 이상 (양 어깨가 좌우로 벌어짐)
    """
    required = ["left_shoulder_x", "right_shoulder_x", "left_hip_y", "left_shoulder_y"]
    if not all(c in df.columns for c in required):
        return 0.0

    dx = (df["left_shoulder_x"] - df["right_shoulder_x"]).abs()
    torso = (df["left_hip_y"] - df["left_shoulder_y"]).abs()
    ratio = (dx / torso).replace([np.inf, -np.inf], np.nan).dropna()
    if len(ratio) == 0:
        return 0.0
    return float(ratio.median())


def assess(
    raw_df: pd.DataFrame,
    fps: float,
    cadence_spm: float,
) -> QualityReport:
    """영상 품질 평가.

    Args:
        raw_df: pose_extractor 의 원본 출력 (전처리 전, visibility 포함).
        fps: 실제 영상 fps.
        cadence_spm: foot strike 기반 분당 보수.

    Returns:
        QualityReport with confidence/warnings/metrics.
    """
    warnings: list[dict] = []
    metrics: dict = {}

    # 1. 검출률.
    ratio = _detected_frame_ratio(raw_df)
    metrics["detected_frame_ratio"] = ratio
    if ratio < MIN_DETECTED_FRAME_RATIO:
        warnings.append({
            "code": "LOW_DETECTION_RATIO",
            "message_ko": (
                f"사람이 검출되지 않은 프레임이 많습니다 ({ratio * 100:.0f}%). "
                "전신이 화면에 들어오도록 촬영해주세요."
            ),
        })

    # 2. 평균 visibility.
    avg_vis = _avg_visibility(raw_df)
    metrics["avg_visibility"] = avg_vis
    if avg_vis < WARN_LOW_AVG_VISIBILITY:
        warnings.append({
            "code": "LOW_VISIBILITY",
            "message_ko": (
                f"관절 인식 신뢰도가 낮습니다 (평균 {avg_vis:.2f}). "
                "조명이 밝은 곳에서 몸에 붙는 옷으로 촬영하면 정확도가 향상됩니다."
            ),
        })

    # 3. 빠른 페이스 + 저fps.
    metrics["cadence_spm"] = cadence_spm
    metrics["fps"] = fps
    if cadence_spm >= WARN_HIGH_CADENCE_SPM and fps < WARN_FPS_FOR_HIGH_CADENCE:
        warnings.append({
            "code": "HIGH_CADENCE_LOW_FPS",
            "message_ko": (
                f"페이스가 빠릅니다 (cadence {cadence_spm:.0f} spm). "
                f"현재 {fps:.0f}fps 로 촬영되어 모션 블러로 정확도가 떨어질 수 있습니다. "
                "60fps 이상 권장."
            ),
        })

    # 4. 측면 각도 이탈.
    side_dev = _side_angle_deviation(raw_df)
    metrics["side_angle_deviation"] = side_dev
    if side_dev > WARN_SIDE_ANGLE_DEVIATION:
        warnings.append({
            "code": "NOT_SIDE_VIEW",
            "message_ko": (
                "측면 촬영이 아닌 것으로 보입니다. "
                "트레드밀 옆에서 골반 높이로 촬영해주세요."
            ),
        })

    # 5. 신뢰도 등급.
    n = len(warnings)
    if n <= CONFIDENCE_HIGH_MAX_WARNINGS:
        confidence = "high"
    elif n <= CONFIDENCE_MEDIUM_MAX_WARNINGS:
        confidence = "medium"
    else:
        confidence = "low"

    logger.info(
        "quality assess: confidence=%s warnings=%d metrics=%s",
        confidence,
        n,
        {k: round(v, 3) if isinstance(v, float) else v for k, v in metrics.items()},
    )
    return QualityReport(confidence=confidence, warnings=warnings, metrics=metrics)


SIDE_VIEW_ASYM_CAUTION = {
    "code": "SIDE_VIEW_ASYM_CAUTION",
    "message_ko": (
        "측면 촬영에서는 카메라 반대쪽 다리의 가림으로 좌우 비대칭 검출에 한계가 "
        "있습니다. 비대칭 결과는 참고용으로 확인해주세요."
    ),
}


def apply_asymmetry_caveats(quality: QualityReport, asym: dict) -> QualityReport:
    """비대칭 워닝이 떴지만 측면 촬영이 의심되지 않을 때 정보성 caveat 카드 추가.

    NOT_SIDE_VIEW 워닝이 이미 있다면 중복 안내를 피해 추가하지 않는다.
    confidence 등급은 변경하지 않는다 — caveat 은 해석 가이드이지 품질 강등이
    아니므로 assess() 단계의 등급 산정을 보존한다.
    """
    if not asym.get("is_warning"):
        return quality
    if any(w["code"] == "NOT_SIDE_VIEW" for w in quality.warnings):
        return quality
    quality.warnings = [*quality.warnings, dict(SIDE_VIEW_ASYM_CAUTION)]
    return quality


__all__ = [
    "QualityReport",
    "assess",
    "SIDE_VIEW_ASYM_CAUTION",
    "apply_asymmetry_caveats",
]
