"""
PRD-7 시나리오 6 (E2E): 거부 영상 6종 실제 합성 + validate() 검증.

기존 test_video_validator 는 monkeypatch 로 메타데이터를 주입하지만, 여기서는
cv2.VideoWriter 로 실제 mp4 파일을 합성하여 cv2.VideoCapture 의 probe → validate
경로가 전부 동작하는지 확인한다.

합성된 영상은 `server/tests/reject_samples/` 에 보관 (session-scoped fixture
캐시) — 앱 측 수동 검증 (시나리오 6 의 i18n 모달 확인) 에 그대로 활용한다.

거부 영상 6종:
  - portrait_720x1280.mp4   → PORTRAIT_NOT_SUPPORTED
  - low_res_640x480.mp4     → RESOLUTION_TOO_LOW
  - low_fps_24fps.mp4       → FPS_TOO_LOW
  - duration_3s.mp4         → DURATION_TOO_SHORT
  - duration_65s.mp4        → DURATION_TOO_LONG
  - corrupt.mp4             → CANNOT_OPEN_VIDEO
"""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pytest

from video_validator import validate

SAMPLE_DIR = Path(__file__).resolve().parent / "reject_samples"


def _write_video(path: Path, w: int, h: int, fps: float, duration_sec: float) -> Path:
    """단색 검정 프레임으로 mp4 합성. mp4v fourcc 사용."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        return path  # 캐시 재사용.
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(path), fourcc, fps, (w, h))
    assert writer.isOpened(), f"VideoWriter open failed: {path}"
    n_frames = max(1, int(round(fps * duration_sec)))
    frame = np.zeros((h, w, 3), dtype=np.uint8)
    for _ in range(n_frames):
        writer.write(frame)
    writer.release()
    return path


@pytest.fixture(scope="session")
def reject_samples() -> dict[str, Path]:
    samples = {
        "portrait": _write_video(SAMPLE_DIR / "portrait_720x1280.mp4", 720, 1280, 30, 8),
        "low_res":  _write_video(SAMPLE_DIR / "low_res_640x480.mp4",   640, 480, 30, 8),
        "low_fps":  _write_video(SAMPLE_DIR / "low_fps_24fps.mp4",     1280, 720, 24, 8),
        "short":    _write_video(SAMPLE_DIR / "duration_3s.mp4",       1280, 720, 60, 3),
        "long":     _write_video(SAMPLE_DIR / "duration_65s.mp4",      1280, 720, 60, 65),
    }
    # corrupt: 헤더 손상 mp4 (텍스트로 채움).
    corrupt = SAMPLE_DIR / "corrupt.mp4"
    if not corrupt.exists():
        corrupt.write_bytes(b"this is not a valid mp4 container")
    samples["corrupt"] = corrupt
    return samples


def test_portrait_rejected(reject_samples):
    r = validate(str(reject_samples["portrait"]))
    assert r.ok is False
    assert r.reason_code == "PORTRAIT_NOT_SUPPORTED"
    assert "가로" in r.reason_message_ko


def test_low_resolution_rejected(reject_samples):
    r = validate(str(reject_samples["low_res"]))
    assert r.ok is False
    assert r.reason_code == "RESOLUTION_TOO_LOW"
    assert "해상도" in r.reason_message_ko


def test_low_fps_rejected(reject_samples):
    r = validate(str(reject_samples["low_fps"]))
    assert r.ok is False
    assert r.reason_code == "FPS_TOO_LOW"
    assert "프레임률" in r.reason_message_ko


def test_too_short_rejected(reject_samples):
    r = validate(str(reject_samples["short"]))
    assert r.ok is False
    assert r.reason_code == "DURATION_TOO_SHORT"
    assert "짧" in r.reason_message_ko


def test_too_long_rejected(reject_samples):
    r = validate(str(reject_samples["long"]))
    assert r.ok is False
    assert r.reason_code == "DURATION_TOO_LONG"
    assert "깁니다" in r.reason_message_ko or "길" in r.reason_message_ko


def test_corrupt_rejected(reject_samples):
    r = validate(str(reject_samples["corrupt"]))
    assert r.ok is False
    assert r.reason_code == "CANNOT_OPEN_VIDEO"
    assert r.meta is None
