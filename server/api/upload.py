"""
영상 업로드 엔드포인트 (PRD-4 Step 2 + Step 3).

책임:
    1. multipart/form-data 로 영상 수신
    2. 확장자 1차 검증 (`.mp4`, `.mov`)
    3. UUID 생성 → `storage/uploads/{analysis_id}.mp4` 로 저장
    4. PRD-8 video_validator.validate() 로 하드 요건 검사
       (cv2 probe 만 사용 — mediapipe 비용 절약)
    5. 거부 시 즉시 파일 삭제 + HTTP 400 + error_code + message_ko
    6. 통과 시 ANALYSIS_STATUS 에 "processing" 으로 등록 + BackgroundTasks 에 분석 큐잉
    7. 202 Accepted + analysis_id 반환

BackgroundTask 내부 (`_run_analysis_task`):
    - `run_full_analysis_with_output` 호출 (mediapipe heavy, ~20~40초)
    - 결과를 ANALYSIS_STATUS[aid] 에 "completed" 로 저장
    - 예외 발생 시 "failed" + 에러 메시지 저장

Step 4 에서 추가될 것:
    - `GET /api/analysis/{id}` 결과 조회 엔드포인트
    - 정적 파일 URL 변환 (rendered_video_path → /storage/renders/...)
"""
from __future__ import annotations

import logging
import shutil
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, UploadFile

from video_validator import validate as validate_video

logger = logging.getLogger(__name__)

router = APIRouter()


# 분석 진행 상태 인메모리 캐시.
# Phase 2 에서 Redis / DB 로 대체. Step 3 의 background task 가 이 dict 를 갱신.
# 키: analysis_id (uuid4 str). 값: {"status": str, "video_path": str, ...}
ANALYSIS_STATUS: dict[str, dict] = {}


# 업로드 받는 위치. main.py 가 startup 시 보장하지만 라우터 단독 import 도 안전하게.
_UPLOADS_DIR = Path(__file__).resolve().parent.parent / "storage" / "uploads"
_UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

# 분석 산출물(렌더링/CSV) 출력 루트. run_full_analysis_with_output 이 그 아래
# renders/, reports/ 서브디렉토리에 저장한다.
_STORAGE_ROOT = Path(__file__).resolve().parent.parent / "storage"


_ALLOWED_EXTS = (".mp4", ".mov", ".webm")


def _to_static_url(path: Path) -> str:
    rel = path.resolve().relative_to(_STORAGE_ROOT.resolve())
    return f"/storage/{rel.as_posix()}"


def _run_analysis_task(analysis_id: str) -> None:
    """
    BackgroundTasks 가 실행하는 분석 작업.

    ANALYSIS_STATUS[analysis_id] 가 "processing" 상태로 이미 등록되어 있어야 한다.
    완료 시 "completed" + result, 실패 시 "failed" + error 로 갱신.

    Lazy import: 라우터 import 시점에 mediapipe / cv2 를 불필요하게 끌어오지 않음.
    """
    entry = ANALYSIS_STATUS.get(analysis_id)
    if entry is None:
        logger.error("background task: unknown analysis_id %s", analysis_id)
        return

    video_path = entry.get("video_path")
    if not video_path or not Path(video_path).exists():
        logger.error("background task: missing video for %s (%s)", analysis_id, video_path)
        ANALYSIS_STATUS[analysis_id] = {
            **entry,
            "status": "failed",
            "error_code": "VIDEO_NOT_FOUND",
            "error_message_ko": "업로드된 영상을 찾을 수 없습니다.",
            "failed_at": datetime.now().isoformat(timespec="seconds"),
        }
        return

    logger.info("background task start: %s", analysis_id)
    started_at = datetime.now()

    # 업로드 시 함께 받은 사용자 입력을 분석으로 전달한다.
    #   - height_cm: VO 가 cm-aware 모드로 동작 (픽셀→cm 환산).
    #   - pace_sec_per_km: cadence 가 pace-aware 모드 (기대 케이던스 범위/hint).
    # 트레드밀 속도(km/h)는 pace(sec/km) 로 환산: pace = 3600 / speed.
    height_cm = entry.get("user_height_cm")
    speed_kmh = entry.get("treadmill_speed_kmh")
    pace_sec_per_km = (
        3600.0 / float(speed_kmh)
        if speed_kmh and float(speed_kmh) > 0
        else None
    )

    try:
        from analyzer import run_full_analysis_with_output

        result = run_full_analysis_with_output(
            video_path=video_path,
            output_dir=str(_STORAGE_ROOT),
            height_cm=float(height_cm) if height_cm else None,
            pace_sec_per_km=pace_sec_per_km,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("background task failed: %s", analysis_id)
        # VideoValidationError 라면 reason_code 가 있을 수 있지만, 업로드 시점에 이미
        # validate 통과한 영상이므로 여기서는 거의 발생하지 않는다 (방어적 처리).
        code = getattr(exc, "code", "ANALYSIS_FAILED")
        message_ko = getattr(exc, "message_ko", None) or "분석 중 오류가 발생했습니다."
        ANALYSIS_STATUS[analysis_id] = {
            **ANALYSIS_STATUS.get(analysis_id, entry),
            "status": "failed",
            "error_code": code,
            "error_message_ko": message_ko,
            "failed_at": datetime.now().isoformat(timespec="seconds"),
        }
        return

    elapsed = (datetime.now() - started_at).total_seconds()
    logger.info("background task done: %s (%.1fs)", analysis_id, elapsed)

    current = ANALYSIS_STATUS.get(analysis_id, entry)
    ANALYSIS_STATUS[analysis_id] = {
        **current,
        "status": "completed",
        "completed_at": datetime.now().isoformat(timespec="seconds"),
        "elapsed_sec": round(elapsed, 2),
        "result": {
            # AnalysisResult 는 Pydantic 모델 → JSON 직렬화는 analysis.py 에서.
            # 일단 원본 객체와 파일 경로를 그대로 보관.
            "analysis_result": result["analysis_result"],
            "rendered_video_path": result["rendered_video_path"],
            "csv_report_path": result["csv_report_path"],
            "coach_message": result["coach_message"],
        },
    }

    # 트레이너 모드: 회원 ID 가 함께 업로드됐다면 히스토리에 등록.
    # Lazy import 로 순환 의존(api.members → api.upload) 회피.
    member_id = current.get("member_id")
    if member_id:
        from api.members import save_to_member_history
        save_to_member_history(member_id, analysis_id)


@router.post("/upload", status_code=202)
async def upload_video(
    background_tasks: BackgroundTasks,
    video: UploadFile = File(...),
    member_id: str | None = Form(None),
    user_height_cm: int | None = Form(None),
    user_weight_kg: int | None = Form(None),
    treadmill_speed_kmh: float | None = Form(None),
) -> dict:
    """
    트레드밀 러닝 영상 업로드 + 비동기 분석 시작.

    영상 수신 + PRD-8 하드 요건 검증 + 임시 저장 + analysis_id 발급 후,
    `run_full_analysis_with_output` 을 BackgroundTasks 로 큐잉하고 즉시 202 반환.
    분석 진행 상태는 `GET /api/analysis/{id}` (Step 4) 에서 조회.

    Form fields:
        video           : mp4 / mov 영상 (필수)
        member_id           : 트레이너 모드의 회원 ID (선택)
        user_height_cm      : 키 (cm, 선택) — VO cm-aware 모드 활성화
        user_weight_kg      : 체중 (kg, 선택)
        treadmill_speed_kmh : 트레드밀 속도 (km/h, 선택) — pace-aware cadence 활성화

    Returns:
        202 Accepted
        {
            "analysis_id": "uuid",
            "status": "processing",
            "estimated_seconds": 30
        }

    Raises:
        400 INVALID_EXTENSION       — 확장자가 .mp4/.mov 가 아님
        400 CANNOT_OPEN_VIDEO       — cv2 가 영상을 열 수 없음
        400 PORTRAIT_NOT_SUPPORTED  — 세로 영상
        400 RESOLUTION_TOO_LOW      — 720p 미만
        400 FPS_TOO_LOW             — 30fps 미만
        400 DURATION_TOO_SHORT      — 5초 미만
        400 DURATION_TOO_LONG       — 60초 초과
    """
    # 1. 확장자 검증 (디스크 쓰기 전).
    filename = video.filename or ""
    if not filename.lower().endswith(_ALLOWED_EXTS):
        raise HTTPException(
            status_code=400,
            detail={
                "error_code": "INVALID_EXTENSION",
                "message_ko": "MP4, MOV 또는 WEBM 파일만 업로드할 수 있습니다.",
            },
        )

    # 2. UUID 발급 + 디스크 저장.
    analysis_id = str(uuid4())
    suffix = Path(filename).suffix.lower() or ".mp4"
    upload_path = _UPLOADS_DIR / f"{analysis_id}{suffix}"
    # UploadFile.file 은 SpooledTemporaryFile. shutil.copyfileobj 가 가장 메모리 효율적.
    try:
        with upload_path.open("wb") as out:
            shutil.copyfileobj(video.file, out)
    finally:
        await video.close()

    logger.info(
        "upload received: %s -> %s (%d bytes)",
        filename,
        upload_path.name,
        upload_path.stat().st_size,
    )

    # 3. PRD-8 하드 요건 검사. mediapipe 호출 전이므로 cv2 probe 만 수행 — 빠름 (~50ms).
    result = validate_video(str(upload_path))
    if not result.ok:
        # 거부된 영상은 디스크에 남기지 않는다 (저장 공간 + 보안).
        upload_path.unlink(missing_ok=True)
        logger.warning(
            "upload rejected by validator: %s (%s)",
            result.reason_code,
            result.reason_message_ko,
        )
        raise HTTPException(
            status_code=400,
            detail={
                "error_code": result.reason_code or "UNKNOWN",
                "message_ko": result.reason_message_ko or "영상 검증에 실패했습니다.",
            },
        )

    # 4. 상태 등록 + 백그라운드 분석 큐잉. 즉시 "processing" 으로 등록한다 — 클라이언트가
    #    202 를 받은 시점부터 분석이 큐에 들어가 있으므로 "uploaded" 와 "processing" 을
    #    구분할 의미가 적다.
    ANALYSIS_STATUS[analysis_id] = {
        "status": "processing",
        "video_path": str(upload_path),
        "member_id": member_id,
        "user_height_cm": user_height_cm,
        "user_weight_kg": user_weight_kg,
        "treadmill_speed_kmh": treadmill_speed_kmh,
        "uploaded_at": datetime.now().isoformat(timespec="seconds"),
    }
    background_tasks.add_task(_run_analysis_task, analysis_id)

    return {
        "analysis_id": analysis_id,
        "status": "processing",
        "estimated_seconds": 30,
        "original_video_url": _to_static_url(upload_path),
    }


__all__ = ["router", "ANALYSIS_STATUS", "_run_analysis_task"]
