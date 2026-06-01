"""
TreadForm FastAPI 엔트리포인트 (PRD-4 Step 1).

현재 Step 1 범위:
    - FastAPI 앱 인스턴스
    - CORS 미들웨어 (모바일 앱이 동일 WiFi LAN 에서 접근)
    - 정적 파일 서빙 (/storage/renders, /storage/reports)
    - 루트 / 헬스체크 엔드포인트

Step 2~5 (현재): upload / analysis / members 라우터 모두 마운트.
    영상 수신 + PRD-8 검증 + BackgroundTasks 분석 + 결과 조회 + 회원/히스토리.
Step 6 이후로 미루는 것:
    - 영속화 (인메모리 ANALYSIS_STATUS / MEMBERS → SQLite/Redis)

실행:
    uvicorn main:app --host 0.0.0.0 --port 8000 --reload

문서: http://localhost:8000/docs
"""
from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from api import analysis, members, upload

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


app = FastAPI(
    title="TreadForm API",
    description="한국형 트레드밀 러닝 자세 분석 서비스 (B2C + 트레이너 모드)",
    version="0.1.0",
)


# CORS: 동일 WiFi LAN 의 모바일 앱이 호출. 개발 단계에서는 전체 허용,
# 운영 단계에서는 화이트리스트로 좁힌다 (PRD-4 흔한 함정 참고).
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# 분석 산출물 (렌더링 영상 / CSV) 다운로드용 정적 마운트.
# storage/ 디렉토리가 없으면 미리 만들어둔다 (StaticFiles 가 디렉토리 부재 시 부팅 실패).
_STORAGE_DIR = Path(__file__).resolve().parent / "storage"
for sub in ("uploads", "renders", "reports"):
    (_STORAGE_DIR / sub).mkdir(parents=True, exist_ok=True)

app.mount("/storage", StaticFiles(directory=str(_STORAGE_DIR)), name="storage")


# 도메인별 라우터.
app.include_router(upload.router, prefix="/api", tags=["upload"])
app.include_router(analysis.router, prefix="/api", tags=["analysis"])
app.include_router(members.router, prefix="/api", tags=["members"])


@app.get("/")
def root() -> dict:
    """서비스 식별용 루트. 앱이 BASE_URL 살아있음을 확인하는 용도."""
    return {"service": "TreadForm", "status": "running", "version": app.version}


@app.get("/health")
def health() -> dict:
    """로드밸런서/모니터링용 헬스체크."""
    return {"status": "healthy"}
