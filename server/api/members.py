"""
회원 관리 엔드포인트 (PRD-4 Step 5 / 트레이너 모드).

B2B 트레이너가 자신의 회원을 등록하고, 회원별 누적 분석 히스토리를 조회한다.
앱(PRD-6)의 비포/애프터 그래프가 이 히스토리를 시간순으로 그린다.

저장소:
    - MEMBERS         : member_id -> 회원 메타데이터
    - MEMBER_HISTORY  : member_id -> [analysis_id, ...] (시간순)
    인메모리. Phase 2 에서 SQLite/PostgreSQL 로 대체.

업로드와의 결합:
    POST /api/upload 의 form field `member_id` 가 설정되면, 분석이 완료된 후
    `save_to_member_history(member_id, analysis_id)` 가 호출되어 히스토리에
    analysis_id 가 append 된다. (upload._run_analysis_task 가 호출)
"""
from __future__ import annotations

import logging
from datetime import datetime
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from api.upload import ANALYSIS_STATUS

logger = logging.getLogger(__name__)

router = APIRouter()


# 인메모리 저장소. Step 6 (영속화) 에서 JSON 백업 추가 예정.
MEMBERS: dict[str, dict] = {}
MEMBER_HISTORY: dict[str, list[str]] = {}


# ---------------------------------------------------------------------------
# 스키마
# ---------------------------------------------------------------------------


class MemberCreate(BaseModel):
    """회원 등록 요청 body."""

    name: str = Field(min_length=1, max_length=50)
    trainer_id: str = Field(min_length=1, max_length=50)


class MemberResponse(BaseModel):
    """회원 정보 응답."""

    member_id: str
    name: str
    trainer_id: str
    created_at: str


# ---------------------------------------------------------------------------
# 엔드포인트
# ---------------------------------------------------------------------------


@router.post("/members", response_model=MemberResponse, status_code=201)
def create_member(member: MemberCreate) -> dict:
    """회원 등록. UUID 발급 후 빈 히스토리와 함께 저장."""
    member_id = str(uuid4())
    entry = {
        "member_id": member_id,
        "name": member.name,
        "trainer_id": member.trainer_id,
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }
    MEMBERS[member_id] = entry
    MEMBER_HISTORY[member_id] = []
    logger.info("member created: %s (%s) by trainer %s", member_id, member.name, member.trainer_id)
    return entry


@router.get("/members", response_model=list[MemberResponse])
def list_members(trainer_id: str) -> list[dict]:
    """특정 트레이너의 모든 회원. trainer_id 는 필수 query parameter."""
    return [m for m in MEMBERS.values() if m["trainer_id"] == trainer_id]


@router.get("/members/{member_id}")
def get_member(member_id: str) -> dict:
    """단일 회원 조회."""
    member = MEMBERS.get(member_id)
    if member is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error_code": "MEMBER_NOT_FOUND",
                "message_ko": "회원을 찾을 수 없습니다.",
            },
        )
    return member


@router.get("/members/{member_id}/history")
def get_member_history(member_id: str) -> dict:
    """
    회원별 누적 분석 히스토리. 비포/애프터 그래프용 가벼운 페이로드만 반환
    (rendered/csv URL 은 포함하지 않음 — `GET /api/analysis/{id}` 로 별도 조회).

    Returns:
        {
            "member_id": "uuid",
            "history": [
                {
                    "analysis_id": "uuid",
                    "completed_at": "2026-...",
                    "summary": {...},
                    "asymmetry": {...},
                    "confidence": "high",
                }, ...
            ]
        }
    """
    if member_id not in MEMBER_HISTORY:
        raise HTTPException(
            status_code=404,
            detail={
                "error_code": "MEMBER_NOT_FOUND",
                "message_ko": "회원을 찾을 수 없습니다.",
            },
        )

    items: list[dict] = []
    for aid in MEMBER_HISTORY[member_id]:
        entry = ANALYSIS_STATUS.get(aid)
        if not entry or entry.get("status") != "completed":
            continue
        ar = (entry.get("result") or {}).get("analysis_result")
        if ar is None:
            continue
        items.append({
            "analysis_id": aid,
            "completed_at": entry.get("completed_at"),
            "summary": ar.summary,
            "asymmetry": ar.asymmetry,
            "confidence": ar.confidence,
        })

    # 분석 완료 시각 오름차순.
    items.sort(key=lambda x: x.get("completed_at") or "")
    return {"member_id": member_id, "history": items}


# ---------------------------------------------------------------------------
# upload.py 가 호출하는 헬퍼
# ---------------------------------------------------------------------------


def save_to_member_history(member_id: str, analysis_id: str) -> None:
    """
    분석 완료 후 호출되어 MEMBER_HISTORY[member_id] 에 analysis_id 를 append.

    member_id 가 등록되지 않은 경우 (앱이 잘못된 ID 를 보냈을 때) 새 entry 를
    만들지 않고 경고만 남긴다 — 회원 등록 API 를 통하지 않은 데이터 누수 방지.
    """
    if member_id not in MEMBER_HISTORY:
        logger.warning(
            "save_to_member_history: unknown member_id %s (analysis_id=%s)",
            member_id, analysis_id,
        )
        return
    MEMBER_HISTORY[member_id].append(analysis_id)
    logger.info(
        "history saved: member=%s analysis=%s (total %d)",
        member_id, analysis_id, len(MEMBER_HISTORY[member_id]),
    )


__all__ = [
    "router",
    "MEMBERS",
    "MEMBER_HISTORY",
    "save_to_member_history",
    "MemberCreate",
    "MemberResponse",
]
