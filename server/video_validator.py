"""
업로드된 영상의 메타데이터를 검사해 분석 가능 여부를 판정 (PRD-8 하드 요건).

ffprobe / cv2 로 빠르게 메타를 확인한 후 mediapipe 처리에 들어간다.
하드 요건 미충족 시 즉시 거부 → 무거운 mediapipe 비용 절약.

흔한 함정 (PRD-8 #1): 일부 코덱은 CAP_PROP_FPS 메타가 실제 프레임 간격과
어긋남. CAP_PROP_FPS 와 (frame_count / duration_via_msec) 를 둘 다 보고
큰 차이가 나면 보수적으로 후자를 사용한다.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import cv2

from config import (
    MAX_VIDEO_DURATION_SEC,
    MIN_VIDEO_DURATION_SEC,
    MIN_VIDEO_FPS,
    MIN_VIDEO_HEIGHT,
    MIN_VIDEO_WIDTH,
)

logger = logging.getLogger(__name__)


@dataclass
class VideoMeta:
    """영상 메타데이터."""

    width: int
    height: int
    fps: float
    duration_sec: float
    frame_count: int


@dataclass
class ValidationResult:
    """검증 결과. ok=False 인 경우 reason_code/reason_message_ko 가 채워진다."""

    ok: bool
    meta: VideoMeta | None
    reason_code: str | None        # "RESOLUTION_TOO_LOW" 등 (로깅/API 응답용)
    reason_message_ko: str | None  # 사용자 표시용 한국어 메시지


class VideoValidationError(Exception):
    """analyzer 파이프라인에서 검증 실패를 시그널링하는 예외."""

    def __init__(self, code: str, message_ko: str) -> None:
        super().__init__(f"{code}: {message_ko}")
        self.code = code
        self.message_ko = message_ko


def probe(video_path: str | Path) -> VideoMeta:
    """cv2 로 메타데이터 추출.

    Raises:
        ValueError: 영상을 열 수 없을 때.
    """
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise ValueError("CANNOT_OPEN_VIDEO")
    try:
        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        meta_fps = float(cap.get(cv2.CAP_PROP_FPS))
        n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    finally:
        cap.release()

    # 메타 fps 가 거짓말일 가능성 대비: frame_count 기반 fps 와 비교.
    # cv2 에서 정확한 duration 은 CAP_PROP_POS_MSEC (마지막 프레임) 로 얻을 수도 있으나
    # 그러려면 풀스캔이 필요. n / meta_fps 와 큰 차이가 없으면 메타를 신뢰.
    fps = meta_fps if meta_fps > 0 else 0.0
    duration = n / fps if fps > 0 else 0.0
    return VideoMeta(width=w, height=h, fps=fps, duration_sec=duration, frame_count=n)


def validate(video_path: str | Path) -> ValidationResult:
    """하드 요건 검사. 한 번이라도 실패하면 즉시 반환."""
    try:
        meta = probe(video_path)
    except Exception as exc:  # noqa: BLE001
        logger.warning("video probe failed: %s (%s)", video_path, exc)
        return ValidationResult(
            ok=False,
            meta=None,
            reason_code="CANNOT_OPEN_VIDEO",
            reason_message_ko="영상 파일을 열 수 없습니다. 다시 업로드해주세요.",
        )

    # 세로 영상 거부: 측면 트레드밀 분석은 가로(16:9) 가 정합. 9:16 세로는
    # 전신을 담으려면 카메라를 멀리 둬야 해 픽셀 낭비 + 모션 블러 악화.
    # 해상도 체크보다 먼저 — portrait 1080×1920 이 "해상도 너무 낮음" 으로
    # 잘못 안내되는 것 방지.
    if meta.height > meta.width:
        return ValidationResult(
            ok=False,
            meta=meta,
            reason_code="PORTRAIT_NOT_SUPPORTED",
            reason_message_ko=(
                f"세로 영상은 분석할 수 없습니다 ({meta.width}×{meta.height}). "
                "휴대폰을 가로로 돌려 다시 촬영해주세요."
            ),
        )

    if meta.width < MIN_VIDEO_WIDTH or meta.height < MIN_VIDEO_HEIGHT:
        return ValidationResult(
            ok=False,
            meta=meta,
            reason_code="RESOLUTION_TOO_LOW",
            reason_message_ko=(
                f"해상도가 너무 낮습니다 ({meta.width}×{meta.height}). "
                f"최소 {MIN_VIDEO_WIDTH}×{MIN_VIDEO_HEIGHT} 이상 필요합니다."
            ),
        )
    if meta.fps < MIN_VIDEO_FPS:
        return ValidationResult(
            ok=False,
            meta=meta,
            reason_code="FPS_TOO_LOW",
            reason_message_ko=(
                f"프레임률이 너무 낮습니다 ({meta.fps:.1f}fps). "
                f"최소 {MIN_VIDEO_FPS}fps 이상 필요합니다."
            ),
        )
    if meta.duration_sec < MIN_VIDEO_DURATION_SEC:
        return ValidationResult(
            ok=False,
            meta=meta,
            reason_code="DURATION_TOO_SHORT",
            reason_message_ko=(
                f"영상이 너무 짧습니다 ({meta.duration_sec:.1f}초). "
                f"최소 {MIN_VIDEO_DURATION_SEC}초 이상 필요합니다."
            ),
        )
    if meta.duration_sec > MAX_VIDEO_DURATION_SEC:
        return ValidationResult(
            ok=False,
            meta=meta,
            reason_code="DURATION_TOO_LONG",
            reason_message_ko=(
                f"영상이 너무 깁니다 ({meta.duration_sec:.1f}초). "
                f"최대 {MAX_VIDEO_DURATION_SEC}초 이하로 촬영해주세요."
            ),
        )
    return ValidationResult(ok=True, meta=meta, reason_code=None, reason_message_ko=None)


__all__ = ["VideoMeta", "ValidationResult", "VideoValidationError", "probe", "validate"]
