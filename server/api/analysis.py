"""
분석 결과 조회 엔드포인트 (PRD-4 Step 4).

`GET /api/analysis/{analysis_id}` — `api.upload.ANALYSIS_STATUS` 에서 상태를 읽고
상태에 맞춰 응답을 변환한다.

상태별 응답:
    - 404 ANALYSIS_NOT_FOUND  — ID 가 존재하지 않음
    - 200 processing           — 분석 진행 중, ETA 와 경과 시간만
    - 200 completed            — 전체 결과 + 정적 파일 URL
    - 200 failed               — error_code + message_ko

정적 파일 URL 변환:
    background task 가 ANALYSIS_STATUS 에 저장한 `rendered_video_path` 는 절대경로
    (예: `C:\\vibeRun\\server\\storage\\renders\\{aid}.mp4`). 클라이언트는 절대경로를
    그대로 받아 쓸 수 없으므로 `/storage/...` 형식으로 변환해 반환.
"""
from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException

from api.upload import ANALYSIS_STATUS

logger = logging.getLogger(__name__)

router = APIRouter()


# main.py 의 StaticFiles 마운트 prefix 와 동일해야 한다.
_STATIC_PREFIX = "/storage"
_STORAGE_ROOT = Path(__file__).resolve().parent.parent / "storage"


def _to_static_url(absolute_path: str | None) -> str | None:
    """`storage/...` 경로를 `/storage/...` URL 로 변환. 외부면 None."""
    if not absolute_path:
        return None
    try:
        rel = Path(absolute_path).resolve().relative_to(_STORAGE_ROOT.resolve())
    except ValueError:
        logger.warning("path is outside storage root: %s", absolute_path)
        return None
    # Windows 경로 구분자 → URL 구분자.
    return f"{_STATIC_PREFIX}/{rel.as_posix()}"


def _seconds_since(iso_ts: str | None) -> float:
    """ISO timestamp 부터 현재까지 경과 초. 파싱 실패 시 0."""
    if not iso_ts:
        return 0.0
    try:
        started = datetime.fromisoformat(iso_ts)
    except ValueError:
        return 0.0
    return max(0.0, (datetime.now() - started).total_seconds())


@router.get("/analysis/{analysis_id}")
def get_analysis(analysis_id: str) -> dict:
    """
    분석 결과/진행 상태 조회.

    Returns:
        - 200 processing : {"status": "processing", "elapsed_sec", "estimated_seconds_remaining"}
        - 200 completed  : {"status": "completed", "analysis_result", "rendered_video_url",
                            "csv_report_url", "coach_message", "elapsed_sec", "completed_at"}
        - 200 failed     : {"status": "failed", "error_code", "error_message_ko", "failed_at"}

    Raises:
        404 ANALYSIS_NOT_FOUND : analysis_id 가 존재하지 않을 때.
    """
    entry = ANALYSIS_STATUS.get(analysis_id)
    if entry is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error_code": "ANALYSIS_NOT_FOUND",
                "message_ko": "해당 분석 ID를 찾을 수 없습니다. 다시 업로드해주세요.",
            },
        )

    status = entry.get("status", "unknown")

    if status == "processing":
        elapsed = _seconds_since(entry.get("uploaded_at"))
        # 일반 영상은 ~30~40초. 음수 방지.
        remaining = max(0.0, 35.0 - elapsed)
        return {
            "analysis_id": analysis_id,
            "status": "processing",
            "elapsed_sec": round(elapsed, 1),
            "estimated_seconds_remaining": round(remaining, 1),
            "original_video_url": _to_static_url(entry.get("video_path")),
        }

    if status == "completed":
        result = entry.get("result") or {}
        ar = result.get("analysis_result")
        ar_payload = ar.model_dump() if ar is not None else None
        return {
            "analysis_id": analysis_id,
            "status": "completed",
            "completed_at": entry.get("completed_at"),
            "elapsed_sec": entry.get("elapsed_sec"),
            "original_video_url": _to_static_url(entry.get("video_path")),
            "rendered_video_url": _to_static_url(result.get("rendered_video_path")),
            "csv_report_url": _to_static_url(result.get("csv_report_path")),
            "coach_message": result.get("coach_message"),
            "analysis_result": ar_payload,
        }

    if status == "failed":
        return {
            "analysis_id": analysis_id,
            "status": "failed",
            "error_code": entry.get("error_code", "ANALYSIS_FAILED"),
            "error_message_ko": entry.get("error_message_ko", "분석에 실패했습니다."),
            "failed_at": entry.get("failed_at"),
        }

    # 알 수 없는 상태 (방어).
    logger.warning("unknown analysis status for %s: %s", analysis_id, status)
    return {
        "analysis_id": analysis_id,
        "status": status,
    }


__all__ = ["router"]
