"""
시각 검증용 디버그 오버레이 영상 생성기.

⚠️ 이건 PRD-3 렌더링 모듈이 아니라 임시 검증 도구다.
   본 렌더링은 PRD-3에서 coach 메시지 + 표준 스타일로 구현된다.

오버레이 내용:
    - 33 keypoints 스켈레톤 (전 프레임)
    - 좌/우 ANKLE, HEEL, FOOT_INDEX 강조 (큰 컬러 점)
    - 착지 프레임에서 0.5초간 큰 마커 + 메트릭 상태 텍스트
        · 무릎 각도 + 4단계 라벨
        · foot strike 각도 + 3단계 라벨
        · overstride 거리
    - 좌상단 HUD: 프레임/시간/누적 카운트
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

import cv2
import numpy as np

from analyzer.foot_strike_detector import detect_left_right_strikes
from analyzer.metrics.foot_strike import (
    calculate_foot_strike_angle,
    classify_foot_strike,
)
from analyzer.metrics.knee_flexion import (
    calculate_knee_angle,
    classify_knee_status,
)
from analyzer.metrics.overstriding import (
    calculate_overstride_distance,
    classify_overstride,
)
from analyzer.pose_extractor import PoseLandmark, extract_pose_series
from analyzer.preprocessor import despike_pose_dataframe, preprocess_pose_dataframe
from config import (
    COLOR_DANGER_BGR,
    COLOR_SAFE_BGR,
    COLOR_WARNING_BGR,
    TARGET_FPS,
)

logger = logging.getLogger(__name__)


# BlazePose 33 landmarks 의 연결선 (간소화 골격).
_CONNECTIONS = [
    # 몸통
    (PoseLandmark.LEFT_SHOULDER, PoseLandmark.RIGHT_SHOULDER),
    (PoseLandmark.LEFT_SHOULDER, PoseLandmark.LEFT_HIP),
    (PoseLandmark.RIGHT_SHOULDER, PoseLandmark.RIGHT_HIP),
    (PoseLandmark.LEFT_HIP, PoseLandmark.RIGHT_HIP),
    # 왼팔
    (PoseLandmark.LEFT_SHOULDER, PoseLandmark.LEFT_ELBOW),
    (PoseLandmark.LEFT_ELBOW, PoseLandmark.LEFT_WRIST),
    # 오른팔
    (PoseLandmark.RIGHT_SHOULDER, PoseLandmark.RIGHT_ELBOW),
    (PoseLandmark.RIGHT_ELBOW, PoseLandmark.RIGHT_WRIST),
    # 왼다리
    (PoseLandmark.LEFT_HIP, PoseLandmark.LEFT_KNEE),
    (PoseLandmark.LEFT_KNEE, PoseLandmark.LEFT_ANKLE),
    (PoseLandmark.LEFT_ANKLE, PoseLandmark.LEFT_HEEL),
    (PoseLandmark.LEFT_HEEL, PoseLandmark.LEFT_FOOT_INDEX),
    (PoseLandmark.LEFT_ANKLE, PoseLandmark.LEFT_FOOT_INDEX),
    # 오른다리
    (PoseLandmark.RIGHT_HIP, PoseLandmark.RIGHT_KNEE),
    (PoseLandmark.RIGHT_KNEE, PoseLandmark.RIGHT_ANKLE),
    (PoseLandmark.RIGHT_ANKLE, PoseLandmark.RIGHT_HEEL),
    (PoseLandmark.RIGHT_HEEL, PoseLandmark.RIGHT_FOOT_INDEX),
    (PoseLandmark.RIGHT_ANKLE, PoseLandmark.RIGHT_FOOT_INDEX),
]

_SKEL_COLOR = (200, 200, 200)


def _xy_px(df, frame: int, side: str, name: str, w: int, h: int) -> tuple[int, int] | None:
    x = df.at[frame, f"{side}_{name}_x"]
    y = df.at[frame, f"{side}_{name}_y"]
    if np.isnan(x) or np.isnan(y):
        return None
    return int(round(x * w)), int(round(y * h))


def _landmark_xy(df, frame: int, lm: PoseLandmark, w: int, h: int) -> tuple[int, int] | None:
    name = lm.name.lower()
    x = df.at[frame, f"{name}_x"]
    y = df.at[frame, f"{name}_y"]
    if np.isnan(x) or np.isnan(y):
        return None
    return int(round(x * w)), int(round(y * h))


def _status_color(status: str) -> tuple[int, int, int]:
    """판정 상태 → BGR."""
    if status in ("heel_strike", "stiff_knee", "over_stride", "high_oscillation"):
        return COLOR_DANGER_BGR
    if status in ("borderline", "forefoot_strike"):
        return COLOR_WARNING_BGR
    return COLOR_SAFE_BGR


def _draw_skeleton(img, df, frame: int, w: int, h: int) -> None:
    for a, b in _CONNECTIONS:
        pa = _landmark_xy(df, frame, a, w, h)
        pb = _landmark_xy(df, frame, b, w, h)
        if pa is None or pb is None:
            continue
        cv2.line(img, pa, pb, _SKEL_COLOR, 2, cv2.LINE_AA)
    # 모든 keypoint 작은 점.
    for lm in PoseLandmark:
        p = _landmark_xy(df, frame, lm, w, h)
        if p is None:
            continue
        cv2.circle(img, p, 3, (180, 180, 180), -1, cv2.LINE_AA)


def _draw_foot_emphasis(img, df, frame: int, w: int, h: int) -> None:
    """ANKLE/HEEL/FOOT_INDEX 를 색상별로 강조."""
    for side in ("left", "right"):
        ankle = _xy_px(df, frame, side, "ankle", w, h)
        heel = _xy_px(df, frame, side, "heel", w, h)
        foot = _xy_px(df, frame, side, "foot_index", w, h)
        if ankle:
            cv2.circle(img, ankle, 6, (0, 255, 255), 2, cv2.LINE_AA)  # 노랑: ankle
        if heel:
            cv2.circle(img, heel, 6, (0, 165, 255), -1, cv2.LINE_AA)  # 주황: heel
        if foot:
            cv2.circle(img, foot, 6, (255, 0, 255), -1, cv2.LINE_AA)  # 마젠타: foot_index


def _put_text(img, text: str, org: tuple[int, int], color=(255, 255, 255), scale=0.55) -> None:
    cv2.putText(img, text, org, cv2.FONT_HERSHEY_SIMPLEX, scale, (0, 0, 0), 3, cv2.LINE_AA)
    cv2.putText(img, text, org, cv2.FONT_HERSHEY_SIMPLEX, scale, color, 1, cv2.LINE_AA)


def _draw_strike_event(
    img,
    df,
    raw_df,
    frame: int,
    side: str,
    w: int,
    h: int,
    y_offset: int,
) -> int:
    """
    한 착지에 대한 마커 + 텍스트.

    스켈레톤 일관성을 위해 마커는 raw_df 좌표로 그리고,
    텍스트의 수치 (knee/foot_strike/overstride) 는 df (preprocessed) 로 계산한다.
    반환: 다음 텍스트 줄의 y.
    """
    hip = np.array(
        [df.at[frame, f"{side}_hip_x"], df.at[frame, f"{side}_hip_y"]], dtype=float
    )
    knee = np.array(
        [df.at[frame, f"{side}_knee_x"], df.at[frame, f"{side}_knee_y"]], dtype=float
    )
    ankle = np.array(
        [df.at[frame, f"{side}_ankle_x"], df.at[frame, f"{side}_ankle_y"]], dtype=float
    )
    heel = np.array(
        [df.at[frame, f"{side}_heel_x"], df.at[frame, f"{side}_heel_y"]], dtype=float
    )
    foot = np.array(
        [df.at[frame, f"{side}_foot_index_x"], df.at[frame, f"{side}_foot_index_y"]],
        dtype=float,
    )

    knee_angle = calculate_knee_angle(hip, knee, ankle)
    knee_status = classify_knee_status(knee_angle)
    fs_angle = calculate_foot_strike_angle(heel, foot)
    fs_status = classify_foot_strike(fs_angle)
    over_d = calculate_overstride_distance(ankle, hip)
    over_status = classify_overstride(over_d)

    # 발 위치에 큰 마커. raw 좌표 사용 → 실제 검출 위치와 정합.
    ankle_px = _xy_px(raw_df, frame, side, "ankle", w, h)
    if ankle_px:
        cv2.circle(img, ankle_px, 18, _status_color(fs_status), 3, cv2.LINE_AA)

    label = f"[{side.upper()} STRIKE @f{frame}]"
    _put_text(img, label, (10, y_offset), (255, 255, 255), 0.6)
    y_offset += 22

    txt = f"  knee {knee_angle:.1f}° [{knee_status}]"
    _put_text(img, txt, (10, y_offset), _status_color(knee_status))
    y_offset += 20

    txt = f"  foot_strike {fs_angle:.1f}° [{fs_status}]"
    _put_text(img, txt, (10, y_offset), _status_color(fs_status))
    y_offset += 20

    txt = f"  overstride {over_d:.3f} [{over_status}]"
    _put_text(img, txt, (10, y_offset), _status_color(over_status))
    y_offset += 24
    return y_offset


def render_debug_video(
    video_path: str,
    output_path: str,
    hold_frames: int = 15,
) -> None:
    """
    Args:
        video_path: 입력 mp4.
        output_path: 출력 mp4.
        hold_frames: 착지 이벤트 텍스트를 표시할 추가 프레임 수.

    파이프라인은 세 단계 좌표를 분리해서 사용한다:
        - raw_df     : mediapipe 원본 (검증/디버그용 보존)
        - despiked   : visibility 마스킹 + Hampel spike 제거. lag 0.
                       → 스켈레톤/마커 가시화에 사용 (튀는 현상 제거된 즉시 추적).
        - df         : despiked + forward fill + EMA. 분석 파이프라인이 사용.
                       → 메트릭 텍스트 수치/착지 인덱스에 사용.
    """
    src = Path(video_path)
    out = Path(output_path)

    logger.info("extracting pose...")
    raw_df = extract_pose_series(str(src))
    despiked_df = despike_pose_dataframe(raw_df)
    df = preprocess_pose_dataframe(raw_df)
    strikes = detect_left_right_strikes(df)
    fps = float(df.attrs.get("fps", TARGET_FPS))

    skeleton_df = despiked_df

    # 프레임 → 진행 중인 strike 이벤트 매핑.
    events: dict[int, list[tuple[str, int]]] = {}
    for side, frames in (("left", strikes["left"]), ("right", strikes["right"])):
        for f in frames:
            f = int(f)
            for k in range(hold_frames + 1):
                events.setdefault(f + k, []).append((side, f))

    cap = cv2.VideoCapture(str(src))
    if not cap.isOpened():
        raise RuntimeError(f"cv2 cannot open: {src}")
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    out.parent.mkdir(parents=True, exist_ok=True)
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(out), fourcc, fps, (w, h))
    if not writer.isOpened():
        raise RuntimeError(f"cv2 VideoWriter open failed: {out}")

    cum_left = 0
    cum_right = 0
    seen_strike_frames: set[int] = set()

    frame_idx = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        if frame_idx >= len(df):
            break

        # 누적 카운트 갱신 (착지 발생 프레임에서만).
        for side, frames in (("left", strikes["left"]), ("right", strikes["right"])):
            if frame_idx in set(int(x) for x in frames):
                if (side, frame_idx) not in seen_strike_frames:
                    seen_strike_frames.add((side, frame_idx))
                    if side == "left":
                        cum_left += 1
                    else:
                        cum_right += 1

        _draw_skeleton(frame, skeleton_df, frame_idx, w, h)
        _draw_foot_emphasis(frame, skeleton_df, frame_idx, w, h)

        # HUD.
        hud = (
            f"frame {frame_idx}/{len(df)-1}  t={frame_idx/fps:.2f}s  "
            f"L={cum_left}  R={cum_right}"
        )
        _put_text(frame, hud, (10, 25), (255, 255, 255), 0.6)

        # 활성 strike 이벤트 텍스트. 마커는 despiked 좌표 (스켈레톤과 정합).
        y = 55
        for side, sf in events.get(frame_idx, []):
            y = _draw_strike_event(frame, df, despiked_df, sf, side, w, h, y)

        # 범례.
        legend_y = h - 70
        _put_text(frame, "ankle=yellow ring  heel=orange  foot_index=magenta",
                  (10, legend_y), (220, 220, 220), 0.5)
        _put_text(frame, "ring color = foot_strike status (red/yellow/green)",
                  (10, legend_y + 18), (220, 220, 220), 0.5)
        _put_text(frame, "text color = metric status",
                  (10, legend_y + 36), (220, 220, 220), 0.5)

        writer.write(frame)
        frame_idx += 1

    cap.release()
    writer.release()
    logger.info("debug overlay saved: %s", out)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    here = Path(__file__).parent
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else here / "running_video.mp4"
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else here / "debug_overlay.mp4"
    if not src.exists():
        print(f"[ERROR] video not found: {src}")
        return 1
    render_debug_video(str(src), str(out))
    print(f"[OK] saved: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
