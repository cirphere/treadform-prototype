"""
3-Layer 스켈레톤 오버레이 영상 렌더링 (PRD-3).

Layer 1: 원본 영상 (720p 베이스)
Layer 2: 스켈레톤 라인 + 착지 시점 강조 (상태별 색상)
Layer 3: 텍스트 오버레이 (한국어 무릎 상태 + 신뢰도 배지)

OpenCV 의 putText 는 한글을 지원하지 않으므로 PIL 로 한글 텍스트를 그린다.
신뢰도 배지/워터마크는 영상 전체에서 변하지 않으므로 첫 프레임에 만든 PIL
오버레이를 캐시해 매 프레임 합성만 한다 (PRD-3 흔한 함정 #9).

좌표 책임 분리:
    스켈레톤은 `skeleton_df` (Hampel + L/R swap 까지만, lag 0) 으로 그린다.
    `preprocess_pose_dataframe()` 의 forward fill + One Euro 가 적용된 좌표는
    빠른 다리 스윙 시 시각적으로 신체에 뒤처지므로 가시화에 부적합 (PRD-3
    흔한 함정 #11). 메트릭 수치는 모두 analysis_result 에서 읽으므로 renderer
    는 keypoints DataFrame 의 분석용 버전이 필요 없다.
"""
from __future__ import annotations

import logging
from pathlib import Path

import cv2
import numpy as np
import pandas as pd
from PIL import Image, ImageDraw, ImageFont

from analyzer.pose_extractor import POSE_CONNECTIONS, PoseLandmark
from analyzer.preprocessor import exponential_moving_average
from config import (
    COLOR_DANGER_BGR,
    COLOR_SAFE_BGR,
    COLOR_WARNING_BGR,
    RENDER_SMOOTHING_ALPHA,
    TARGET_FPS,
)
from models.analysis_result import AnalysisResult

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 폰트
# ---------------------------------------------------------------------------

# 시스템별 한글 폰트 후보. 첫 번째로 발견되는 것을 사용.
_FONT_CANDIDATES = [
    # Windows
    "C:/Windows/Fonts/malgun.ttf",
    "C:/Windows/Fonts/malgunbd.ttf",
    "C:/Windows/Fonts/gulim.ttc",
    # macOS
    "/System/Library/Fonts/AppleSDGothicNeo.ttc",
    "/Library/Fonts/AppleSDGothicNeo.ttc",
    # Linux (nanum)
    "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
    "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf",
]


def _find_korean_font() -> str | None:
    """시스템에서 첫 번째로 발견되는 한글 폰트 경로 반환. 없으면 None."""
    for p in _FONT_CANDIDATES:
        if Path(p).exists():
            return p
    return None


def _load_font(size: int) -> ImageFont.FreeTypeFont:
    """한글 폰트 로드. 실패 시 PIL 기본 폰트로 fallback (한글 깨질 수 있음)."""
    path = _find_korean_font()
    if path is None:
        logger.warning("Korean font not found; using PIL default (Korean may not render)")
        return ImageFont.load_default()
    return ImageFont.truetype(path, size)


# ---------------------------------------------------------------------------
# 상태 → 색상
# ---------------------------------------------------------------------------


def _status_color_bgr(status: str) -> tuple[int, int, int]:
    if status in ("heel_strike", "stiff_knee", "over_stride", "high_oscillation"):
        return COLOR_DANGER_BGR
    if status in ("borderline", "forefoot_strike", "over_bent"):
        return COLOR_WARNING_BGR
    return COLOR_SAFE_BGR


def _confidence_color_bgr(confidence: str) -> tuple[int, int, int]:
    if confidence == "high":
        return COLOR_SAFE_BGR
    if confidence == "medium":
        return COLOR_WARNING_BGR
    return COLOR_DANGER_BGR


_CONFIDENCE_KO = {"high": "높음", "medium": "보통", "low": "낮음"}


# ---------------------------------------------------------------------------
# 스켈레톤
# ---------------------------------------------------------------------------


def _landmark_xy_px(
    keypoints: dict, lm: PoseLandmark, w: int, h: int
) -> tuple[int, int] | None:
    name = lm.name.lower()
    x = keypoints.get(f"{name}_x")
    y = keypoints.get(f"{name}_y")
    if x is None or y is None:
        return None
    if isinstance(x, float) and np.isnan(x):
        return None
    if isinstance(y, float) and np.isnan(y):
        return None
    return int(round(float(x) * w)), int(round(float(y) * h))


def draw_skeleton_on_frame(
    frame: np.ndarray,
    keypoints: dict,
    color_bgr: tuple[int, int, int],
) -> np.ndarray:
    """
    한 프레임에 스켈레톤 라인을 그린다.

    Args:
        frame: BGR ndarray (in-place 수정).
        keypoints: {landmark_name_x/y/...} dict (정규화 좌표).
        color_bgr: 스켈레톤 라인 색상.

    Returns:
        수정된 frame (in-place 이지만 chain 편의를 위해 반환).
    """
    h, w = frame.shape[:2]
    for a, b in POSE_CONNECTIONS:
        pa = _landmark_xy_px(keypoints, a, w, h)
        pb = _landmark_xy_px(keypoints, b, w, h)
        if pa is None or pb is None:
            continue
        cv2.line(frame, pa, pb, color_bgr, 2, cv2.LINE_AA)
    # keypoint dot 들.
    for lm in PoseLandmark:
        p = _landmark_xy_px(keypoints, lm, w, h)
        if p is None:
            continue
        cv2.circle(frame, p, 3, color_bgr, -1, cv2.LINE_AA)
    return frame


def emphasize_foot_strike(
    frame: np.ndarray,
    ankle_position: tuple[int, int],
    color_bgr: tuple[int, int, int],
) -> np.ndarray:
    """착지 시점 발목 위치에 큰 강조 원."""
    cv2.circle(frame, ankle_position, 20, color_bgr, 3, cv2.LINE_AA)
    return frame


# ---------------------------------------------------------------------------
# 한글 텍스트 (PIL)
# ---------------------------------------------------------------------------


def _bgr_to_rgb(color_bgr: tuple[int, int, int]) -> tuple[int, int, int]:
    return color_bgr[2], color_bgr[1], color_bgr[0]


def draw_text_overlay(
    frame: np.ndarray,
    knee_angle: float,
    status_text_ko: str,
    color_bgr: tuple[int, int, int],
    origin: tuple[int, int] = (20, 60),
    font_size: int = 26,
) -> np.ndarray:
    """
    한국어 상태 텍스트를 PIL 로 그려 frame 위에 합성.

    Args:
        frame: BGR ndarray.
        knee_angle: 무릎 각도(°). NaN 이면 표기 생략.
        status_text_ko: 한국어 상태 라벨.
        color_bgr: 텍스트 색상.
        origin: (x, y) 시작 좌표.
        font_size: 폰트 크기.

    Returns:
        새 BGR ndarray (원본은 보존).
    """
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    img = Image.fromarray(rgb)
    draw = ImageDraw.Draw(img)
    font = _load_font(font_size)

    if isinstance(knee_angle, float) and not np.isnan(knee_angle):
        line = f"무릎 {knee_angle:.1f}°  {status_text_ko}"
    else:
        line = status_text_ko

    # 검은색 그림자 → 색상 본문 (가독성).
    draw.text((origin[0] + 1, origin[1] + 1), line, font=font, fill=(0, 0, 0))
    draw.text(origin, line, font=font, fill=_bgr_to_rgb(color_bgr))

    return cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)


# ---------------------------------------------------------------------------
# 신뢰도 배지 (캐시)
# ---------------------------------------------------------------------------


def _build_confidence_overlay(
    width: int,
    height: int,
    confidence: str,
) -> np.ndarray:
    """
    좌상단 신뢰도 배지 + (low 일 경우) 좌하단 워터마크가 그려진 BGRA 오버레이.

    매 프레임 동일하므로 한 번만 생성해 캐시한다.
    """
    overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    badge_font = _load_font(20)

    color_rgb = _bgr_to_rgb(_confidence_color_bgr(confidence))
    label_ko = _CONFIDENCE_KO.get(confidence, confidence)

    # 좌상단 배지: 200 x 40.
    box = (10, 10, 210, 50)
    draw.rectangle(box, fill=(0, 0, 0, 160), outline=color_rgb + (255,), width=2)
    draw.text((20, 18), f"신뢰도: {label_ko}", font=badge_font, fill=color_rgb + (255,))

    if confidence == "low":
        watermark_font = _load_font(22)
        text = "참고용 — 재촬영 권장"
        # 좌하단.
        y = height - 40
        draw.text((11, y + 1), text, font=watermark_font, fill=(0, 0, 0, 220))
        draw.text((10, y), text, font=watermark_font,
                  fill=_bgr_to_rgb(COLOR_DANGER_BGR) + (220,))

    # PIL RGBA → cv2 BGRA.
    arr = np.array(overlay)
    return cv2.cvtColor(arr, cv2.COLOR_RGBA2BGRA)


def _composite_bgra(frame_bgr: np.ndarray, overlay_bgra: np.ndarray) -> np.ndarray:
    """
    BGR frame 위에 BGRA overlay 를 알파 블렌딩으로 합성. in-place.
    """
    if overlay_bgra.shape[:2] != frame_bgr.shape[:2]:
        raise ValueError(
            f"overlay shape {overlay_bgra.shape[:2]} != frame {frame_bgr.shape[:2]}"
        )
    alpha = overlay_bgra[:, :, 3:4].astype(np.float32) / 255.0
    rgb = overlay_bgra[:, :, :3].astype(np.float32)
    base = frame_bgr.astype(np.float32)
    blended = base * (1.0 - alpha) + rgb * alpha
    frame_bgr[:] = blended.astype(np.uint8)
    return frame_bgr


# ---------------------------------------------------------------------------
# 메인 렌더링
# ---------------------------------------------------------------------------


_KNEE_STATUS_KO = {
    "stiff_knee": "무릎 경직 (위험)",
    "good_flexion": "정상",
    "over_bent": "과굴곡 (주의)",
    "borderline": "경계",
}


_COORD_SUFFIXES = ("_x", "_y", "_z")
_VISIBILITY_SUFFIX = "_visibility"


def smooth_skeleton_df(
    df: pd.DataFrame,
    alpha: float = RENDER_SMOOTHING_ALPHA,
) -> pd.DataFrame:
    """
    가시화 전용 약한 EMA. 좌표 컬럼(_x/_y/_z)만 평활화한다.

    분석 파이프라인의 EMA_ALPHA(0.3) 보다 명확히 크게(0.6 기본) 두어 lag 을
    1~2 프레임 수준으로 제한한다. visibility / frame_idx / timestamp_sec 등은
    그대로 둔다. NaN 은 평활화에서 streak reset 으로 처리되어 그대로 NaN 유지.

    Args:
        df: 보통 `despike_pose_dataframe()` 결과.
        alpha: 평활 계수 (0~1). 1.0 이면 입력을 그대로 반환.

    Returns:
        새 DataFrame (원본 attrs 유지).
    """
    if alpha >= 1.0:
        return df

    out = df.copy()
    for col in out.columns:
        if not col.endswith(_COORD_SUFFIXES):
            continue
        if col.endswith(_VISIBILITY_SUFFIX):
            continue
        out[col] = exponential_moving_average(
            out[col].to_numpy(dtype=float), alpha=alpha
        )
    out.attrs.update(df.attrs)
    return out


def _frame_keypoints(skeleton_df: pd.DataFrame, frame_idx: int) -> dict:
    """DataFrame 에서 한 프레임 행을 dict 로."""
    if frame_idx < 0 or frame_idx >= len(skeleton_df):
        return {}
    return skeleton_df.iloc[frame_idx].to_dict()


def _build_strike_index(metrics: dict) -> dict[int, dict]:
    """frame_idx → {knee, foot_strike, overstride, foot} 빠른 조회."""
    idx: dict[int, dict] = {}
    for entry in metrics.get("knee_flexion", {}).get("per_strike", []):
        slot = idx.setdefault(int(entry["frame"]), {"foot": entry.get("foot", "")})
        slot["knee"] = entry
    for entry in metrics.get("foot_strike", {}).get("per_strike", []):
        slot = idx.setdefault(int(entry["frame"]), {"foot": entry.get("foot", "")})
        slot["foot_strike"] = entry
    for entry in metrics.get("overstriding", {}).get("per_strike", []):
        slot = idx.setdefault(int(entry["frame"]), {"foot": entry.get("foot", "")})
        slot["overstride"] = entry
    return idx


def render_skeleton_video(
    input_video_path: str,
    output_video_path: str,
    skeleton_df: pd.DataFrame,
    analysis_result: AnalysisResult,
    strike_hold_frames: int = 8,
    smoothing_alpha: float = RENDER_SMOOTHING_ALPHA,
) -> str:
    """
    원본 영상에 스켈레톤/한국어 텍스트/신뢰도 배지를 합성한 MP4 생성.

    Args:
        input_video_path: 원본 mp4.
        output_video_path: 출력 mp4 경로.
        skeleton_df: 가시화용 keypoints DataFrame. `despike_pose_dataframe()`
            결과 (Hampel + L/R swap 까지 적용, forward fill / One Euro 미적용)
            를 권장. 분석용 `preprocess_pose_dataframe()` 결과를 넘기면 빠른
            움직임에서 스켈레톤이 신체에 뒤처진다.
        analysis_result: 분석 결과 (metrics, confidence, warnings 포함).
            모든 메트릭 수치/per_strike 인덱스는 여기에서 읽으므로 별도의
            분석용 DataFrame 은 필요 없다.
        strike_hold_frames: 착지 시점에 강조 마커를 유지할 추가 프레임 수.
        smoothing_alpha: 가시화 전용 EMA 계수. 기본 RENDER_SMOOTHING_ALPHA(0.6).
            1.0 이면 평활화를 끄고 despiked 원본을 그대로 사용 (디버그 용도).

    Returns:
        출력 영상 절대 경로.

    Raises:
        FileNotFoundError: 입력 영상 없을 때.
        RuntimeError: cv2 열기/쓰기 실패 시.
    """
    src = Path(input_video_path)
    if not src.exists():
        raise FileNotFoundError(f"video not found: {src}")
    out = Path(output_video_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    cap = cv2.VideoCapture(str(src))
    if not cap.isOpened():
        raise RuntimeError(f"cv2 cannot open: {src}")

    # 가시화 전용 약한 EMA — inter-frame jitter 감소, lag ~1프레임.
    skeleton_df = smooth_skeleton_df(skeleton_df, alpha=smoothing_alpha)

    fps = float(skeleton_df.attrs.get("fps") or cap.get(cv2.CAP_PROP_FPS) or TARGET_FPS)
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(out), fourcc, fps, (w, h))
    if not writer.isOpened():
        cap.release()
        raise RuntimeError(f"cv2 VideoWriter open failed: {out}")

    strike_idx = _build_strike_index(analysis_result.metrics)
    # 어느 프레임에서 어떤 strike 가 활성화되는지 (hold_frames 지속).
    active_strikes: dict[int, list[int]] = {}
    for sf in strike_idx.keys():
        for k in range(strike_hold_frames + 1):
            active_strikes.setdefault(sf + k, []).append(sf)

    # 신뢰도 오버레이는 영상 전체에서 동일 → 캐시.
    confidence_overlay = _build_confidence_overlay(w, h, analysis_result.confidence)

    frame_idx = 0
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            if frame_idx >= len(skeleton_df):
                break

            kp = _frame_keypoints(skeleton_df, frame_idx)

            # 현재 프레임의 기본 스켈레톤 색상은 그 시점에 활성화된 worst status 로 결정.
            worst_color = COLOR_SAFE_BGR
            active_text_color = COLOR_SAFE_BGR
            knee_angle = float("nan")
            knee_status_ko: str | None = None

            for sf in active_strikes.get(frame_idx, []):
                slot = strike_idx.get(sf, {})
                knee_entry = slot.get("knee")
                fs_entry = slot.get("foot_strike")
                over_entry = slot.get("overstride")
                for entry in (knee_entry, fs_entry, over_entry):
                    if entry is None:
                        continue
                    c = _status_color_bgr(entry.get("status", ""))
                    if c == COLOR_DANGER_BGR:
                        worst_color = COLOR_DANGER_BGR
                    elif c == COLOR_WARNING_BGR and worst_color != COLOR_DANGER_BGR:
                        worst_color = COLOR_WARNING_BGR

                # 텍스트는 가장 최근(=가장 이른) 활성 strike 의 knee 정보로 표시.
                if knee_entry is not None and (knee_status_ko is None):
                    knee_angle = float(knee_entry.get("angle", float("nan")))
                    knee_status_ko = _KNEE_STATUS_KO.get(
                        knee_entry.get("status", ""), knee_entry.get("status", "")
                    )
                    active_text_color = _status_color_bgr(knee_entry.get("status", ""))

            draw_skeleton_on_frame(frame, kp, worst_color)

            # 착지 시점(sf == frame_idx) 발목 강조.
            for sf in active_strikes.get(frame_idx, []):
                if sf != frame_idx:
                    continue
                slot = strike_idx.get(sf, {})
                foot = slot.get("foot", "")
                if foot not in ("left", "right"):
                    continue
                ankle_lm = (
                    PoseLandmark.LEFT_ANKLE if foot == "left" else PoseLandmark.RIGHT_ANKLE
                )
                ankle_px = _landmark_xy_px(kp, ankle_lm, w, h)
                if ankle_px is None:
                    continue
                fs_entry = slot.get("foot_strike", {})
                emphasize_foot_strike(
                    frame, ankle_px, _status_color_bgr(fs_entry.get("status", ""))
                )

            # 한국어 텍스트 (knee 상태가 있을 때만).
            if knee_status_ko is not None:
                frame = draw_text_overlay(
                    frame, knee_angle, knee_status_ko, active_text_color
                )

            # 신뢰도 배지 / 워터마크 합성 (캐시된 BGRA).
            _composite_bgra(frame, confidence_overlay)

            writer.write(frame)
            frame_idx += 1
    finally:
        cap.release()
        writer.release()

    logger.info(
        "render done: %s frames=%d fps=%.2f confidence=%s",
        out.name,
        frame_idx,
        fps,
        analysis_result.confidence,
    )
    return str(out.resolve())


__all__ = [
    "render_skeleton_video",
    "draw_skeleton_on_frame",
    "draw_text_overlay",
    "emphasize_foot_strike",
    "smooth_skeleton_df",
]
