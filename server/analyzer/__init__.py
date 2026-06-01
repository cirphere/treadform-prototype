"""
analyzer 패키지.

Step 1 (pose 추출/전처리/착지 판별) + Step 2 (3대 지표 계산) + Step 3
(렌더링/한국어 코칭/CSV) 를 통합한 end-to-end 분석 파이프라인을 노출한다.

공개 진입점:
    - run_full_analysis(video_path) -> AnalysisResult
    - run_full_analysis_with_output(video_path, output_dir) -> dict
      (Step 3 산출물까지 포함)

무거운 의존성(cv2, mediapipe)을 가진 pose_extractor / renderer 는 lazy import 한다.
"""
from __future__ import annotations

import logging
import uuid
from pathlib import Path

from config import TARGET_FPS

logger = logging.getLogger(__name__)


def _frame_to_sec(frame_idx: int, fps: float) -> float:
    """프레임 인덱스를 초 단위 timestamp 로 변환."""
    if fps <= 0:
        fps = TARGET_FPS
    return round(frame_idx / fps, 3)


def _collect_danger_timestamps(metrics: dict, fps: float):
    """각 지표의 per_strike/per_stride 중 위험(🔴) 상태만 모아 타임스탬프화."""
    from models.analysis_result import DangerTimestamp

    danger: list[DangerTimestamp] = []

    for entry in metrics["knee_flexion"]["per_strike"]:
        if entry["status"] == "stiff_knee":
            danger.append(
                DangerTimestamp(
                    time_sec=_frame_to_sec(entry["frame"], fps),
                    type="stiff_knee",
                )
            )

    for entry in metrics["foot_strike"]["per_strike"]:
        if entry["status"] == "heel_strike":
            danger.append(
                DangerTimestamp(
                    time_sec=_frame_to_sec(entry["frame"], fps),
                    type="heel_strike",
                )
            )

    for entry in metrics["overstriding"]["per_strike"]:
        if entry["status"] == "over_stride":
            danger.append(
                DangerTimestamp(
                    time_sec=_frame_to_sec(entry["frame"], fps),
                    type="over_stride",
                )
            )

    for entry in metrics["vertical_oscillation"]["per_stride"]:
        if entry["status"] == "high_oscillation":
            danger.append(
                DangerTimestamp(
                    time_sec=_frame_to_sec(entry["start_frame"], fps),
                    type="high_oscillation",
                )
            )

    danger.sort(key=lambda d: d.time_sec)
    return danger


def _validate_or_raise(video_path: str) -> None:
    from video_validator import VideoValidationError, validate

    validation = validate(video_path)
    if not validation.ok:
        logger.warning(
            "validation rejected: %s (%s)",
            validation.reason_code,
            validation.reason_message_ko,
        )
        raise VideoValidationError(
            validation.reason_code or "UNKNOWN",
            validation.reason_message_ko or "영상 검증에 실패했습니다.",
        )


def _avg_foot_visibility(raw_df, side: str) -> float:
    """좌 또는 우 발(heel/foot_index/ankle) 의 visibility 평균.

    `analyze_asymmetry` 에 넘겨 좌/우 검출 신뢰도 차이로 strike_count 비대칭
    신호를 무력화시키는 데 사용 (occlusion 으로 한쪽이 안 잡힌 경우 자동 식별).
    """
    cols = [
        f"{side}_heel_visibility",
        f"{side}_foot_index_visibility",
        f"{side}_ankle_visibility",
    ]
    available = [c for c in cols if c in raw_df.columns]
    if not available or len(raw_df) == 0:
        return float("nan")
    return float(raw_df[available].mean(skipna=True).mean())


def _analyze_from_raw_df(
    raw_df,
    video_path: str,
    height_cm: float | None = None,
    pace_sec_per_km: float | None = None,
):
    """raw_df 가 이미 추출됐다고 가정하고 분석 수행. (AnalysisResult, df) 반환.

    height_cm 가 주어지면 VO 가 cm-aware 모드로 동작 (프레임 내 nose~ankle 정규화
    길이로 픽셀→cm 환산). 미주어지면 기존 정규화 임계 fallback.

    pace_sec_per_km 가 주어지면 cadence 가 pace-aware 모드로 동작 — summary 에
    expected_cadence_min/max + cadence_deviation_pct + cadence_hint 추가. 미주어지면
    summary 는 기존 cadence_spm 필드만 노출 (기존 동작 보존).
    """
    from analyzer import quality_assessor
    from analyzer.body_scale import compute_body_norm_length
    from analyzer.cadence_calibrator import (
        calculate_expected_cadence_range,
        classify_cadence,
    )
    from analyzer.foot_strike_detector import detect_left_right_strikes
    from analyzer.metrics.asymmetry import analyze_asymmetry
    from analyzer.metrics.foot_strike import analyze_foot_strike
    from analyzer.metrics.knee_flexion import analyze_knee_flexion
    from analyzer.metrics.overstriding import analyze_overstriding
    from analyzer.metrics.vertical_osc import analyze_vertical_oscillation
    from analyzer.preprocessor import preprocess_pose_dataframe
    from models.analysis_result import AnalysisResult, QualityWarning

    df = preprocess_pose_dataframe(raw_df)
    strikes = detect_left_right_strikes(df)

    knee = analyze_knee_flexion(df, strikes)
    foot = analyze_foot_strike(df, strikes)
    over = analyze_overstriding(df, strikes)
    body_norm_length = compute_body_norm_length(df) if height_cm else None
    vosc = analyze_vertical_oscillation(
        df, strikes,
        height_cm=height_cm,
        body_norm_length=body_norm_length,
    )

    metrics = {
        "knee_flexion": knee,
        "foot_strike": foot,
        "overstriding": over,
        "vertical_oscillation": vosc,
    }
    foot_visibility = {
        "left": _avg_foot_visibility(raw_df, "left"),
        "right": _avg_foot_visibility(raw_df, "right"),
    }
    asym = analyze_asymmetry(strikes, knee, vosc, foot_visibility=foot_visibility)

    fps = float(df.attrs.get("fps", TARGET_FPS))
    danger = _collect_danger_timestamps(metrics, fps)

    total_strikes = len(strikes["left"]) + len(strikes["right"])
    duration_min = (len(df) / fps / 60.0) if fps > 0 and len(df) > 0 else 0.0
    cadence_spm = (total_strikes / duration_min) if duration_min > 0 else 0.0

    quality = quality_assessor.assess(raw_df, fps=fps, cadence_spm=cadence_spm)
    quality = quality_assessor.apply_asymmetry_caveats(quality, asym)

    summary = {
        "total_frames": int(len(df)),
        "duration_sec": float(df["timestamp_sec"].iloc[-1]) if len(df) else 0.0,
        "fps": fps,
        "total_strikes": int(total_strikes),
        "left_strikes": int(len(strikes["left"])),
        "right_strikes": int(len(strikes["right"])),
        "danger_count": len(danger),
        "cadence_spm": round(cadence_spm, 1),
    }

    # Cadence pace-aware 보정 (Phase 2, 2026-05-28).
    # pace 주어지지 않으면 expected range 필드는 summary 에 미추가 (기존 동작 보존).
    expected_rng = calculate_expected_cadence_range(pace_sec_per_km, height_cm)
    if expected_rng is not None:
        cad_lo, cad_hi = expected_rng
        cls = classify_cadence(cadence_spm, cad_lo, cad_hi)
        summary["expected_cadence_min"] = cad_lo
        summary["expected_cadence_max"] = cad_hi
        summary["cadence_hint"] = cls["hint"]
        summary["cadence_deviation_pct"] = cls["deviation_pct"]
        summary["pace_sec_per_km"] = float(pace_sec_per_km)

    result = AnalysisResult(
        analysis_id=Path(video_path).stem + "-" + uuid.uuid4().hex[:8],
        summary=summary,
        metrics=metrics,
        asymmetry=asym,
        danger_timestamps=danger,
        confidence=quality.confidence,
        warnings=[QualityWarning(**w) for w in quality.warnings],
    )
    logger.info(
        "analysis done: strikes=%d, danger=%d, confidence=%s, warnings=%d",
        summary["total_strikes"],
        summary["danger_count"],
        quality.confidence,
        len(quality.warnings),
    )
    return result, df


def run_full_analysis(
    video_path: str,
    height_cm: float | None = None,
    pace_sec_per_km: float | None = None,
):
    """
    영상 1개에 대해 전체 분석 파이프라인을 실행.

    파이프라인 (PRD-8 적용):
        1. video_validator.validate() — 하드 요건 (해상도/fps/길이). 실패 시 VideoValidationError.
        2. extract_pose_series() — MediaPipe Tasks API pose 추출 (raw_df 보관).
        3. preprocess_pose_dataframe() — 5단계 전처리.
        4. detect_left_right_strikes() + analyze_* — 3대 지표.
        5. quality_assessor.assess(raw_df, fps, cadence) — confidence/warnings.

    Args:
        video_path: 입력 mp4 절대 경로.
        height_cm: 사용자 신장(cm). 주어지면 VO 가 cm-aware 모드 (Phase 1).
        pace_sec_per_km: 이번 세션 목표 pace (sec/km). 주어지면 cadence 가
            pace-aware 모드 — summary 에 expected_cadence_min/max + hint 추가.

    Returns:
        models.analysis_result.AnalysisResult

    Raises:
        video_validator.VideoValidationError: 하드 요건 미충족 시.
    """
    from analyzer.pose_extractor import extract_pose_series

    logger.info(
        "run_full_analysis start: %s (height_cm=%s pace_sec_per_km=%s)",
        video_path, height_cm, pace_sec_per_km,
    )

    _validate_or_raise(video_path)
    raw_df = extract_pose_series(video_path)
    result, _ = _analyze_from_raw_df(
        raw_df, video_path,
        height_cm=height_cm,
        pace_sec_per_km=pace_sec_per_km,
    )
    return result


def run_full_analysis_with_output(
    video_path: str,
    output_dir: str,
    height_cm: float | None = None,
    pace_sec_per_km: float | None = None,
) -> dict:
    """
    Step 1+2+3+8 모든 처리를 한 번에 실행 (PRD-3).

    내부 호출 순서:
        1. _validate_or_raise + extract_pose_series  → raw_df (1회만)
        2. _analyze_from_raw_df → (AnalysisResult, 분석용 df)  (PRD-1+2+8)
        3. despike_pose_dataframe(raw_df) → skeleton_df (가시화용 lag 0)
        4. renderer.render_skeleton_video(...)             (PRD-3)
        5. csv_reporter.generate_csv_report(...)           (PRD-3)
        6. coach_message.generate_korean_coach_message(...) (PRD-3)

    raw_df 는 한 번만 추출하여 분석 + skeleton_df 생성에 재사용한다 (PRD-7
    벤치마크 최적화, 2026-05-16). 이전엔 run_full_analysis 안에서 1회,
    이 함수에서 1회 — 총 2회 extract_pose_series 가 호출돼 60fps 11초
    영상이 약 165초가 걸렸다.

    Args:
        video_path: 입력 mp4 절대 경로.
        output_dir: storage 루트. `renders/` 와 `reports/` 서브디렉토리에 산출물 저장.

    Raises:
        video_validator.VideoValidationError: PRD-8 하드 요건 위반 시.

    Returns:
        {
            "analysis_result": AnalysisResult,    # confidence/warnings 포함
            "rendered_video_path": str,
            "csv_report_path": str,
            "coach_message": str,
        }
    """
    from analyzer import coach_message, csv_reporter, renderer
    from analyzer.pose_extractor import extract_pose_series
    from analyzer.preprocessor import despike_pose_dataframe

    _validate_or_raise(video_path)

    # raw_df 1회만 추출 후 분석/렌더링이 공유.
    raw_df = extract_pose_series(video_path)
    analysis_result, df = _analyze_from_raw_df(
        raw_df, video_path,
        height_cm=height_cm,
        pace_sec_per_km=pace_sec_per_km,
    )

    # skeleton_df: Hampel + L/R swap 만 적용 (lag 0 가시화용).
    #   분석용 df 를 쓰면 One Euro 평활 lag 때문에 빠른 다리 스윙에서
    #   스켈레톤이 신체에 뒤처져 그려진다 (PRD-3 흔한 함정 #11).
    skeleton_df = despike_pose_dataframe(raw_df)

    out_root = Path(output_dir)
    renders_dir = out_root / "renders"
    reports_dir = out_root / "reports"
    renders_dir.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)

    analysis_id = analysis_result.analysis_id
    rendered_path = renders_dir / f"{analysis_id}.mp4"
    csv_path = reports_dir / f"{analysis_id}.csv"

    # 3. 렌더링 (skeleton_df 사용 — lag 0).
    rendered = renderer.render_skeleton_video(
        input_video_path=video_path,
        output_video_path=str(rendered_path),
        skeleton_df=skeleton_df,
        analysis_result=analysis_result,
    )

    # 4. CSV (분석용 df 사용 — hip_y 가 평활된 분석 좌표와 정합).
    csv = csv_reporter.generate_csv_report(
        output_csv_path=str(csv_path),
        keypoints_df=df,
        analysis_result=analysis_result,
    )

    # 5. 한국어 코칭.
    message = coach_message.generate_korean_coach_message(analysis_result)

    logger.info(
        "run_full_analysis_with_output done: %s render=%s csv=%s",
        analysis_id,
        rendered_path.name,
        csv_path.name,
    )
    return {
        "analysis_result": analysis_result,
        "rendered_video_path": rendered,
        "csv_report_path": csv,
        "coach_message": message,
    }


__all__ = ["run_full_analysis", "run_full_analysis_with_output"]
