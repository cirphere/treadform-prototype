"""
video_validator 단위 테스트 (PRD-8 하드 요건).

probe 는 실제 cv2 호출이 필요하므로 monkeypatch 로 메타데이터를 주입한다.
실제 영상 파일이 있는 경우 통합 테스트로 한 번 확인.
"""
from __future__ import annotations

from pathlib import Path

import pytest

import video_validator
from video_validator import (
    VideoMeta,
    VideoValidationError,
    ValidationResult,
    validate,
)

REAL_VIDEO = Path(__file__).resolve().parents[1] / "pace530.mp4"


def _meta(
    *,
    width: int = 1280,
    height: int = 720,
    fps: float = 60.0,
    duration_sec: float = 10.0,
    frame_count: int = 300,
) -> VideoMeta:
    return VideoMeta(
        width=width,
        height=height,
        fps=fps,
        duration_sec=duration_sec,
        frame_count=frame_count,
    )


def _patch_probe(monkeypatch: pytest.MonkeyPatch, meta: VideoMeta) -> None:
    monkeypatch.setattr(video_validator, "probe", lambda _: meta)


class TestHardRequirements:
    def test_passes_valid_video(self, monkeypatch):
        _patch_probe(monkeypatch, _meta())
        r = validate("dummy.mp4")
        assert r.ok is True
        assert r.reason_code is None
        assert r.meta is not None

    def test_rejects_low_resolution(self, monkeypatch):
        _patch_probe(monkeypatch, _meta(width=640, height=480))
        r = validate("dummy.mp4")
        assert r.ok is False
        assert r.reason_code == "RESOLUTION_TOO_LOW"
        assert "해상도" in r.reason_message_ko

    def test_rejects_low_height_only(self, monkeypatch):
        # width 는 충분하나 height 가 부족한 케이스.
        _patch_probe(monkeypatch, _meta(width=1920, height=600))
        r = validate("dummy.mp4")
        assert r.ok is False
        assert r.reason_code == "RESOLUTION_TOO_LOW"

    def test_rejects_low_fps(self, monkeypatch):
        _patch_probe(monkeypatch, _meta(fps=24.0))
        r = validate("dummy.mp4")
        assert r.ok is False
        assert r.reason_code == "FPS_TOO_LOW"

    def test_rejects_too_short(self, monkeypatch):
        _patch_probe(monkeypatch, _meta(duration_sec=3.0, frame_count=90))
        r = validate("dummy.mp4")
        assert r.ok is False
        assert r.reason_code == "DURATION_TOO_SHORT"

    def test_rejects_too_long(self, monkeypatch):
        _patch_probe(monkeypatch, _meta(duration_sec=120.0, frame_count=3600))
        r = validate("dummy.mp4")
        assert r.ok is False
        assert r.reason_code == "DURATION_TOO_LONG"

    def test_rejects_portrait_video(self, monkeypatch):
        # 1080×1920 세로 영상 — 해상도 자체는 충분하지만 portrait 거부.
        _patch_probe(monkeypatch, _meta(width=1080, height=1920))
        r = validate("dummy.mp4")
        assert r.ok is False
        assert r.reason_code == "PORTRAIT_NOT_SUPPORTED"
        assert "가로로" in r.reason_message_ko

    def test_square_video_not_portrait(self, monkeypatch):
        # 정사각형은 portrait 가 아니므로 다음 검사(RESOLUTION) 로 넘어감.
        _patch_probe(monkeypatch, _meta(width=720, height=720))
        r = validate("dummy.mp4")
        assert r.ok is False
        assert r.reason_code == "RESOLUTION_TOO_LOW"

    def test_handles_corrupt_file(self, monkeypatch):
        def _raise(_):
            raise ValueError("CANNOT_OPEN_VIDEO")

        monkeypatch.setattr(video_validator, "probe", _raise)
        r = validate("nonexistent.mp4")
        assert r.ok is False
        assert r.reason_code == "CANNOT_OPEN_VIDEO"
        assert r.meta is None


class TestBoundaryValues:
    def test_exact_min_resolution_passes(self, monkeypatch):
        _patch_probe(monkeypatch, _meta(width=1280, height=720))
        assert validate("dummy.mp4").ok is True

    def test_exact_min_fps_passes(self, monkeypatch):
        _patch_probe(monkeypatch, _meta(fps=60.0))
        assert validate("dummy.mp4").ok is True

    def test_exact_min_duration_passes(self, monkeypatch):
        _patch_probe(monkeypatch, _meta(duration_sec=5.0, frame_count=150))
        assert validate("dummy.mp4").ok is True

    def test_exact_max_duration_passes(self, monkeypatch):
        _patch_probe(monkeypatch, _meta(duration_sec=60.0, frame_count=1800))
        assert validate("dummy.mp4").ok is True


class TestException:
    def test_video_validation_error_carries_code(self):
        exc = VideoValidationError("FPS_TOO_LOW", "프레임률이 너무 낮습니다.")
        assert exc.code == "FPS_TOO_LOW"
        assert "프레임률" in exc.message_ko
        assert "FPS_TOO_LOW" in str(exc)


@pytest.mark.skipif(not REAL_VIDEO.exists(), reason="pace530.mp4 not present")
class TestRealVideo:
    def test_real_running_video_passes(self):
        r = validate(str(REAL_VIDEO))
        assert r.ok is True, f"Expected pass but got: {r.reason_code} {r.reason_message_ko}"
        assert r.meta.width >= 1280
        assert r.meta.fps >= 60
