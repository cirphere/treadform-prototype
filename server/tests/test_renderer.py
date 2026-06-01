"""
PRD-3 renderer 단위 테스트.

cv2 로 합성 영상을 만들고 합성 keypoints DataFrame + AnalysisResult 를 입력해
출력 영상의 존재/해상도/길이를 확인한다. mediapipe 호출은 일절 하지 않는다.
"""
from __future__ import annotations

import math
from pathlib import Path

import cv2
import numpy as np
import pandas as pd
import pytest

from analyzer.pose_extractor import PoseLandmark
from analyzer.renderer import (
    _build_confidence_overlay,
    draw_skeleton_on_frame,
    draw_text_overlay,
    render_skeleton_video,
    smooth_skeleton_df,
)
from config import COLOR_DANGER_BGR, COLOR_SAFE_BGR
from models.analysis_result import AnalysisResult


WIDTH = 320
HEIGHT = 240
FPS = 30
N_FRAMES = 30  # 1초.


def _synth_video(path: Path) -> None:
    """단색 + 글자가 살짝 있는 합성 mp4."""
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(path), fourcc, FPS, (WIDTH, HEIGHT))
    assert writer.isOpened()
    for i in range(N_FRAMES):
        frame = np.full((HEIGHT, WIDTH, 3), 30, dtype=np.uint8)
        cv2.putText(frame, str(i), (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
        writer.write(frame)
    writer.release()


def _synth_keypoints_row(t: float) -> dict:
    """모든 33 landmark 를 화면 중앙 근처에 배치, 시간에 따라 살짝 흔들림."""
    row: dict = {}
    base = {
        PoseLandmark.NOSE: (0.5, 0.15),
        PoseLandmark.LEFT_SHOULDER: (0.45, 0.28),
        PoseLandmark.RIGHT_SHOULDER: (0.55, 0.28),
        PoseLandmark.LEFT_ELBOW: (0.40, 0.40),
        PoseLandmark.RIGHT_ELBOW: (0.60, 0.40),
        PoseLandmark.LEFT_WRIST: (0.38, 0.50),
        PoseLandmark.RIGHT_WRIST: (0.62, 0.50),
        PoseLandmark.LEFT_HIP: (0.45, 0.55),
        PoseLandmark.RIGHT_HIP: (0.55, 0.55),
        PoseLandmark.LEFT_KNEE: (0.44, 0.72),
        PoseLandmark.RIGHT_KNEE: (0.56, 0.72),
        PoseLandmark.LEFT_ANKLE: (0.43, 0.88),
        PoseLandmark.RIGHT_ANKLE: (0.57, 0.88),
        PoseLandmark.LEFT_HEEL: (0.42, 0.90),
        PoseLandmark.RIGHT_HEEL: (0.58, 0.90),
        PoseLandmark.LEFT_FOOT_INDEX: (0.45, 0.91),
        PoseLandmark.RIGHT_FOOT_INDEX: (0.55, 0.91),
    }
    jitter = 0.005 * math.sin(t * 2 * math.pi)
    for lm in PoseLandmark:
        x, y = base.get(lm, (0.5, 0.5))
        name = lm.name.lower()
        row[f"{name}_x"] = x + jitter
        row[f"{name}_y"] = y + jitter
        row[f"{name}_z"] = 0.0
        row[f"{name}_visibility"] = 1.0
    return row


def _synth_dataframe() -> pd.DataFrame:
    rows = []
    for i in range(N_FRAMES):
        row = {"frame_idx": i, "timestamp_sec": i / FPS}
        row.update(_synth_keypoints_row(i / FPS))
        rows.append(row)
    df = pd.DataFrame(rows)
    df.attrs["fps"] = float(FPS)
    return df


def _synth_result(confidence: str = "high") -> AnalysisResult:
    return AnalysisResult(
        analysis_id="renderer-test",
        summary={
            "total_frames": N_FRAMES,
            "duration_sec": N_FRAMES / FPS,
            "fps": float(FPS),
            "total_strikes": 2,
            "left_strikes": 1,
            "right_strikes": 1,
            "danger_count": 1,
            "cadence_spm": 120.0,
        },
        metrics={
            "knee_flexion": {
                "avg_angle": 150.0,
                "left_avg": 150.0,
                "right_avg": 150.0,
                "status_counts": {"stiff": 1, "good": 1, "over_bent": 0, "borderline": 0},
                "per_strike": [
                    {"frame": 10, "angle": 165.0, "status": "stiff_knee", "foot": "left"},
                    {"frame": 20, "angle": 150.0, "status": "good_flexion", "foot": "right"},
                ],
            },
            "foot_strike": {
                "status_counts": {"heel": 1, "midfoot": 1, "forefoot": 0},
                "per_strike": [
                    {"frame": 10, "angle": -10.0, "status": "heel_strike", "foot": "left"},
                    {"frame": 20, "angle": 0.0, "status": "mid_foot_strike", "foot": "right"},
                ],
            },
            "overstriding": {
                "avg_distance": 0.1,
                "status_counts": {"good": 2, "over": 0},
                "per_strike": [
                    {"frame": 10, "distance": 0.10, "status": "good_stride", "foot": "left"},
                    {"frame": 20, "distance": 0.11, "status": "good_stride", "foot": "right"},
                ],
            },
            "vertical_oscillation": {
                "avg_value": 0.05,
                "left_avg": 0.05,
                "right_avg": 0.05,
                "status": "good",
                "per_stride": [],
            },
        },
        asymmetry={
            "strike_count_ratio": 0.0,
            "knee_angle_ratio": 0.0,
            "oscillation_ratio": 0.0,
            "is_warning": False,
        },
        confidence=confidence,
    )


# ---------------------------------------------------------------------------
# 통합: 출력 영상
# ---------------------------------------------------------------------------


def test_render_video_exists(tmp_path: Path):
    src = tmp_path / "in.mp4"
    out = tmp_path / "out.mp4"
    _synth_video(src)
    df = _synth_dataframe()
    result = _synth_result()

    returned = render_skeleton_video(str(src), str(out), df, result)
    assert Path(returned).exists()
    assert out.stat().st_size > 0


def test_render_video_resolution_and_frames(tmp_path: Path):
    src = tmp_path / "in.mp4"
    out = tmp_path / "out.mp4"
    _synth_video(src)
    df = _synth_dataframe()
    result = _synth_result()

    render_skeleton_video(str(src), str(out), df, result)

    cap = cv2.VideoCapture(str(out))
    assert cap.isOpened()
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    cap.release()

    assert (w, h) == (WIDTH, HEIGHT)
    # 입력과 동일한 프레임 수.
    assert frame_count == N_FRAMES


def test_render_missing_input_raises(tmp_path: Path):
    df = _synth_dataframe()
    result = _synth_result()
    with pytest.raises(FileNotFoundError):
        render_skeleton_video(
            str(tmp_path / "nope.mp4"),
            str(tmp_path / "out.mp4"),
            df,
            result,
        )


# ---------------------------------------------------------------------------
# 유닛: 보조 함수들
# ---------------------------------------------------------------------------


def test_draw_skeleton_modifies_frame():
    frame = np.zeros((HEIGHT, WIDTH, 3), dtype=np.uint8)
    kp = _synth_keypoints_row(0.0)
    draw_skeleton_on_frame(frame, kp, COLOR_SAFE_BGR)
    # 무엇이라도 그려졌어야 함.
    assert frame.sum() > 0


def test_draw_skeleton_skips_nan():
    frame = np.zeros((HEIGHT, WIDTH, 3), dtype=np.uint8)
    kp = _synth_keypoints_row(0.0)
    # 한 landmark 를 NaN 으로.
    kp["left_hip_x"] = float("nan")
    kp["left_hip_y"] = float("nan")
    # 예외 없이 그려져야.
    draw_skeleton_on_frame(frame, kp, COLOR_SAFE_BGR)


def test_draw_text_overlay_returns_new_frame():
    frame = np.zeros((HEIGHT, WIDTH, 3), dtype=np.uint8)
    out = draw_text_overlay(frame, 150.0, "정상", COLOR_SAFE_BGR)
    assert out.shape == frame.shape
    # 텍스트 픽셀이 어딘가에 찍혔어야 함.
    assert out.sum() > 0


def test_confidence_overlay_low_has_watermark():
    overlay_high = _build_confidence_overlay(WIDTH, HEIGHT, "high")
    overlay_low = _build_confidence_overlay(WIDTH, HEIGHT, "low")
    # low 는 워터마크로 픽셀이 더 많이 사용되어야.
    assert overlay_low[:, :, 3].sum() > overlay_high[:, :, 3].sum()


def test_render_low_confidence_runs(tmp_path: Path):
    src = tmp_path / "in.mp4"
    out = tmp_path / "out.mp4"
    _synth_video(src)
    df = _synth_dataframe()
    result = _synth_result(confidence="low")
    render_skeleton_video(str(src), str(out), df, result)
    assert out.exists()


# ---------------------------------------------------------------------------
# 가시화 전용 평활화 (smooth_skeleton_df)
# ---------------------------------------------------------------------------


def _jittery_dataframe(n: int = 100, noise_amp: float = 0.02) -> pd.DataFrame:
    """랜덤 jitter 가 섞인 합성 좌표."""
    rng = np.random.default_rng(42)
    rows = []
    for i in range(n):
        row = {"frame_idx": i, "timestamp_sec": i / FPS}
        base = _synth_keypoints_row(i / FPS)
        for k, v in base.items():
            if k.endswith(("_x", "_y", "_z")):
                row[k] = v + rng.normal(0, noise_amp)
            else:
                row[k] = v
        rows.append(row)
    df = pd.DataFrame(rows)
    df.attrs["fps"] = float(FPS)
    return df


def test_smooth_reduces_jitter():
    df = _jittery_dataframe()
    smoothed = smooth_skeleton_df(df, alpha=0.6)
    # 좌표 컬럼의 frame-to-frame 변동(diff) 표준편차가 줄어야.
    raw_diff_std = df["left_hip_x"].diff().std()
    smooth_diff_std = smoothed["left_hip_x"].diff().std()
    assert smooth_diff_std < raw_diff_std


def test_smooth_alpha_one_is_identity():
    df = _jittery_dataframe()
    out = smooth_skeleton_df(df, alpha=1.0)
    # α=1.0 → 그대로 반환 (input ref 동일성도 OK).
    pd.testing.assert_frame_equal(out, df)


def test_smooth_preserves_attrs():
    df = _jittery_dataframe()
    smoothed = smooth_skeleton_df(df, alpha=0.6)
    assert smoothed.attrs.get("fps") == float(FPS)


def test_smooth_preserves_non_coord_columns():
    df = _jittery_dataframe()
    smoothed = smooth_skeleton_df(df, alpha=0.6)
    # frame_idx / timestamp_sec / visibility 는 그대로.
    pd.testing.assert_series_equal(smoothed["frame_idx"], df["frame_idx"])
    pd.testing.assert_series_equal(smoothed["timestamp_sec"], df["timestamp_sec"])
    pd.testing.assert_series_equal(
        smoothed["left_hip_visibility"], df["left_hip_visibility"]
    )


def test_smooth_preserves_nan():
    df = _jittery_dataframe(n=10)
    df.loc[3, "left_hip_x"] = float("nan")
    smoothed = smooth_skeleton_df(df, alpha=0.6)
    assert np.isnan(smoothed.loc[3, "left_hip_x"])
    # 비-NaN 인덱스는 NaN 이 아니어야.
    assert not np.isnan(smoothed.loc[0, "left_hip_x"])
    assert not np.isnan(smoothed.loc[5, "left_hip_x"])
