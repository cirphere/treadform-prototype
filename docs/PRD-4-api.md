# PRD-4: FastAPI 서버 엔드포인트

> 📍 항상 함께 참조: **[PRD-0-context.md](./PRD-0-context.md)**
> 📍 이전 단계 산출물: **[PRD-3-render-coach.md](./PRD-3-render-coach.md)**
> 📍 교차 참조: **[PRD-8-video-input-spec.md](./PRD-8-video-input-spec.md)** (검증 실패 응답, confidence/warnings 필드)

---

## 🎯 이 단계의 목표

Step 1~3에서 완성된 분석 엔진을 FastAPI 엔드포인트로 노출하여, **동일 WiFi LAN에서 모바일 앱이 호출할 수 있는 HTTP 서버**를 완성한다. 영상 업로드, 분석 진행, 결과 조회, 회원 관리(트레이너 모드) 전체 API를 구현.

---

## 📥 입력 (의존성)

- **이전 단계 산출물**:
    - `run_full_analysis()` 통합 함수 (PRD-1 + PRD-2 + PRD-8 구현 완료, PRD-3 의 렌더링·코칭은 별도 호출로 결합)
    - 렌더링 영상 + CSV + 한국어 코칭 메시지 (PRD-3)
    - `VideoValidationError` 예외 (PRD-8) → HTTP 400 매핑
- **필수 참조**: `PRD-0-context.md`, `PRD-3-render-coach.md`, `PRD-8-video-input-spec.md`

---

## ✅ 완료 조건 (Definition of Done)

- [ ] FastAPI 앱이 `0.0.0.0:8000`에서 동작
- [ ] `POST /api/upload` 영상 수신 및 비동기 분석 시작
- [ ] `POST /api/upload` 가 PRD-8 하드 요건 위반 시 **HTTP 400 + `error_code` + `message_ko`** 반환 (mediapipe 호출 전)
- [ ] `GET /api/analysis/{id}` 결과 조회 (processing/completed/failed)
- [ ] 분석 결과 응답에 PRD-8 의 `confidence` + `warnings` 동봉
- [ ] `POST /api/members` 회원 등록 (트레이너 모드)
- [ ] `GET /api/members/{id}/history` 회원별 누적 결과
- [ ] 정적 파일 서빙 (`/storage/renders/*.mp4`, `/storage/reports/*.csv`)
- [ ] CORS 설정 (모바일 앱 접근 허용)
- [ ] 동시 다중 분석 요청 처리 (BackgroundTasks)
- [ ] OpenAPI 문서 자동 생성 (`/docs`)
- [ ] curl로 end-to-end 테스트 통과 (정상 영상 1건 + 거부 영상 1건)
- [ ] 외부 디바이스(모바일/타 PC)에서 호출 가능 확인

---

## 📋 작업 항목

### 1. `server/main.py` 엔트리포인트

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from api import upload, analysis, members

app = FastAPI(
    title="TreadForm API",
    description="한국형 트레드밀 러닝 자세 분석 서비스",
    version="1.0.0"
)

# CORS (모바일 앱이 동일 WiFi에서 접근)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 프로젝트 단계, 운영 시에는 화이트리스트
    allow_methods=["*"],
    allow_headers=["*"],
)

# 정적 파일 (렌더링 영상, CSV 다운로드용)
app.mount("/storage", StaticFiles(directory="storage"), name="storage")

# API 라우터
app.include_router(upload.router, prefix="/api")
app.include_router(analysis.router, prefix="/api")
app.include_router(members.router, prefix="/api")

@app.get("/")
def root():
    return {"service": "TreadForm", "status": "running"}

@app.get("/health")
def health():
    return {"status": "healthy"}
```

### 2. `server/api/upload.py` — 영상 업로드 엔드포인트

```python
from fastapi import APIRouter, UploadFile, File, BackgroundTasks, Form, HTTPException
from uuid import uuid4
import os

from video_validator import validate as validate_video  # PRD-8

router = APIRouter()

# 분석 진행 상태 저장소 (간단한 인메모리 캐시; Phase 2에서 Redis로 대체)
ANALYSIS_STATUS: dict[str, dict] = {}

@router.post("/upload", status_code=202)
async def upload_video(
    background_tasks: BackgroundTasks,
    video: UploadFile = File(...),
    member_id: str | None = Form(None),
    user_height_cm: int | None = Form(None),
    user_weight_kg: int | None = Form(None),
):
    """
    트레드밀 러닝 영상 업로드 및 비동기 분석 시작.

    Returns:
        202 Accepted
        {"analysis_id": "uuid", "status": "processing", "estimated_seconds": 30}

    Raises:
        HTTP 400: 확장자/하드 요건 (PRD-8) 위반.
            {"error_code": "FPS_TOO_LOW", "message_ko": "프레임률이 너무 낮습니다..."}
    """
    # 1. 영상 확장자 검증.
    if not video.filename.endswith((".mp4", ".mov")):
        raise HTTPException(
            status_code=400,
            detail={
                "error_code": "INVALID_EXTENSION",
                "message_ko": "MP4 또는 MOV 파일만 허용됩니다.",
            },
        )

    # 2. UUID 생성 및 디스크 저장.
    analysis_id = str(uuid4())
    upload_path = f"storage/uploads/{analysis_id}.mp4"
    os.makedirs("storage/uploads", exist_ok=True)
    with open(upload_path, "wb") as f:
        f.write(await video.read())

    # 3. PRD-8 하드 요건 검증 (mediapipe 비용 절약 위해 background 진입 전에).
    validation = validate_video(upload_path)
    if not validation.ok:
        os.remove(upload_path)  # 거부된 영상은 즉시 삭제.
        raise HTTPException(
            status_code=400,
            detail={
                "error_code": validation.reason_code,
                "message_ko": validation.reason_message_ko,
            },
        )

    # 4. 상태 초기화 + 백그라운드 분석.
    ANALYSIS_STATUS[analysis_id] = {
        "status": "processing",
        "member_id": member_id,
        "started_at": datetime.now().isoformat(),
    }
    background_tasks.add_task(
        run_analysis_task,
        analysis_id=analysis_id,
        video_path=upload_path,
        member_id=member_id,
    )

    return {
        "analysis_id": analysis_id,
        "status": "processing",
        "estimated_seconds": 30,
    }


def run_analysis_task(analysis_id: str, video_path: str, member_id: str | None):
    """백그라운드에서 실행되는 분석 작업.

    참고: validate() 는 업로드 시점에 이미 수행했지만, run_full_analysis_with_output
    내부에서 한 번 더 호출해도 안전 (probe 비용 ~50ms 미만).
    """
    from analyzer import run_full_analysis_with_output

    try:
        # PRD-3 통합 함수 — 분석 + 렌더링 + CSV + 코칭을 한 번에 산출.
        # PRD-7 (2026-05-16) raw_df 캐싱 후 extract_pose_series 는 1회만 호출됨.
        out = run_full_analysis_with_output(video_path, STORAGE_ROOT)

        ANALYSIS_STATUS[analysis_id] = {
            "status": "completed",
            "result": {
                "analysis_result": out["analysis_result"],
                "rendered_video_url": f"/storage/renders/{Path(out['rendered_video_path']).name}",
                "csv_report_url":     f"/storage/reports/{Path(out['csv_report_path']).name}",
                "coach_message": out["coach_message"],
            },
            "member_id": member_id,
            "completed_at": datetime.now().isoformat(),
        }

        if member_id:
            save_to_member_history(member_id, analysis_id, ANALYSIS_STATUS[analysis_id]["result"])

    except Exception as e:
        ANALYSIS_STATUS[analysis_id] = {
            "status": "failed",
            "error": str(e),
        }
```

> 📌 **검증 위치 선택**: 하드 요건 검사를 (1) 업로드 직후 동기 단계, (2) `run_analysis_task` 백그라운드 단계 중 어디서 할지는 트레이드오프. 위 예시는 **동기 단계** 선택 — 사용자가 401/400 응답을 즉시 받아 재촬영할 수 있게. 단점은 업로드 트래픽 낭비 (거부될 영상도 디스크에 한 번 떨어진 뒤 삭제). 대형 영상이 많아지면 클라이언트가 메타데이터만 먼저 보내고 사전 검증하는 `POST /api/precheck` 엔드포인트 추가 검토.

### 3. `server/api/analysis.py` — 분석 결과 조회

```python
@router.get("/analysis/{analysis_id}")
def get_analysis(analysis_id: str):
    """
    분석 결과 조회.

    Returns:
        - processing: 아직 분석 중
        - completed: 결과 포함
        - failed: 에러 메시지
    """
    if analysis_id not in ANALYSIS_STATUS:
        raise HTTPException(404, "분석 ID를 찾을 수 없습니다.")

    state = ANALYSIS_STATUS[analysis_id]

    if state["status"] == "processing":
        return {
            "analysis_id": analysis_id,
            "status": "processing",
        }

    if state["status"] == "failed":
        return {
            "analysis_id": analysis_id,
            "status": "failed",
            "error": state["error"],
        }

    # 완료된 결과 반환 (Step 3 산출물 + PRD-8 confidence/warnings).
    result = state["result"]
    ar = result["analysis_result"]
    return {
        "analysis_id": analysis_id,
        "status": "completed",
        "rendered_video_url": f"/storage/renders/{analysis_id}.mp4",
        "csv_url": f"/storage/reports/{analysis_id}.csv",
        "summary": ar.summary,
        "metrics": ar.metrics,
        "asymmetry": ar.asymmetry,
        "danger_timestamps": [ts.model_dump() for ts in ar.danger_timestamps],
        "coach_message_ko": result["coach_message"],
        # PRD-8 품질 평가.
        "confidence": ar.confidence,                     # "high" | "medium" | "low"
        "warnings": [w.model_dump() for w in ar.warnings],  # [{code, message_ko}, ...]
    }
```

### 4. `server/api/members.py` — 회원 관리 (트레이너 모드)

```python
from pydantic import BaseModel

# 인메모리 회원 저장소 (Phase 2: SQLite/PostgreSQL로 대체)
MEMBERS: dict[str, dict] = {}
MEMBER_HISTORY: dict[str, list] = {}  # member_id -> [analysis_id, ...]

class MemberCreate(BaseModel):
    name: str
    trainer_id: str

class MemberResponse(BaseModel):
    member_id: str
    name: str
    trainer_id: str
    created_at: str

@router.post("/members", response_model=MemberResponse)
def create_member(member: MemberCreate):
    """회원 등록 (트레이너 모드)."""
    member_id = str(uuid4())
    MEMBERS[member_id] = {
        **member.model_dump(),
        "member_id": member_id,
        "created_at": datetime.now().isoformat(),
    }
    MEMBER_HISTORY[member_id] = []
    return MEMBERS[member_id]

@router.get("/members")
def list_members(trainer_id: str):
    """특정 트레이너의 모든 회원 조회."""
    return [m for m in MEMBERS.values() if m["trainer_id"] == trainer_id]

@router.get("/members/{member_id}/history")
def get_member_history(member_id: str):
    """
    회원별 누적 분석 결과 (비포/애프터 그래프용).

    Returns:
        [{
            "analysis_id": "uuid",
            "date": "2025-...",
            "summary": {...},
            "metrics": {...}
        }, ...]
    """
    if member_id not in MEMBER_HISTORY:
        raise HTTPException(404, "회원을 찾을 수 없습니다.")

    history = []
    for aid in MEMBER_HISTORY[member_id]:
        if aid in ANALYSIS_STATUS and ANALYSIS_STATUS[aid]["status"] == "completed":
            result = ANALYSIS_STATUS[aid]["result"]
            history.append({
                "analysis_id": aid,
                "date": ANALYSIS_STATUS[aid]["completed_at"],
                "summary": result["analysis_result"].summary,
                "metrics": result["analysis_result"].metrics,
            })

    return {"member_id": member_id, "history": history}

def save_to_member_history(member_id: str, analysis_id: str, result: dict):
    """upload.py의 백그라운드 작업에서 호출."""
    if member_id in MEMBER_HISTORY:
        MEMBER_HISTORY[member_id].append(analysis_id)
```

### 5. `server/api/__init__.py` 모듈 export

```python
from . import upload, analysis, members

__all__ = ["upload", "analysis", "members"]
```

### 6. 데이터 영속화 (간단 버전)

Phase 1 MVP에서는 **인메모리 저장**이지만, 서버 재시작 시 데이터 보존을 위해 JSON 파일 백업:

```python
# server/storage/state_persistence.py
import json
import os

STATE_FILE = "storage/state.json"

def save_state():
    """서버 종료 시 상태 저장."""
    with open(STATE_FILE, "w") as f:
        json.dump({
            "members": MEMBERS,
            "member_history": MEMBER_HISTORY,
        }, f, ensure_ascii=False, indent=2)

def load_state():
    """서버 시작 시 상태 로드."""
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            data = json.load(f)
            MEMBERS.update(data.get("members", {}))
            MEMBER_HISTORY.update(data.get("member_history", {}))
```

### 7. `requirements.txt` 업데이트

```
fastapi>=0.110.0
uvicorn[standard]>=0.27.0
python-multipart>=0.0.9
mediapipe>=0.10.35          # Tasks API (legacy mp.solutions 제거됨)
opencv-python>=4.9.0
numpy>=1.26.0
scipy>=1.12.0
pandas>=2.2.0
pydantic>=2.6.0
Pillow>=10.0.0
```

### 7a. 에러 코드 카탈로그 (PRD-8 매핑)

`POST /api/upload` 가 반환할 수 있는 `error_code` 전체. 클라이언트(PRD-5/6) 의 i18n 매핑 기준.

| HTTP | error_code | 사용자 메시지 (자동 생성) | 발생 시점 |
|---|---|---|---|
| 400 | `INVALID_EXTENSION` | MP4 또는 MOV 파일만 허용됩니다. | 확장자 검사 |
| 400 | `CANNOT_OPEN_VIDEO` | 영상 파일을 열 수 없습니다. 다시 업로드해주세요. | cv2 디코드 실패 |
| 400 | `PORTRAIT_NOT_SUPPORTED` | 세로 영상은 분석할 수 없습니다. 휴대폰을 가로로 돌려 다시 촬영해주세요. | 세로 영상 |
| 400 | `RESOLUTION_TOO_LOW` | 해상도가 너무 낮습니다... | 1280×720 미만 |
| 400 | `FPS_TOO_LOW` | 프레임률이 너무 낮습니다... | 30fps 미만 |
| 400 | `DURATION_TOO_SHORT` | 영상이 너무 짧습니다... | 5초 미만 |
| 400 | `DURATION_TOO_LONG` | 영상이 너무 깁니다... | 60초 초과 |

> 📌 클라이언트는 `error_code` 로 i18n 키를 매핑하되, 폴백으로 서버의 `message_ko` 를 그대로 표시해도 안전 (서버가 한국어 메시지 생성 책임을 가짐).

### 8. 테스트 작성

`server/tests/test_api.py`

```python
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200

def test_upload_video():
    with open("samples/test_run_3s.mp4", "rb") as f:
        response = client.post(
            "/api/upload",
            files={"video": ("test.mp4", f, "video/mp4")},
        )
    assert response.status_code == 202
    assert "analysis_id" in response.json()

def test_get_analysis_not_found():
    response = client.get("/api/analysis/nonexistent-id")
    assert response.status_code == 404

def test_upload_rejects_portrait_video():
    # PRD-8: 세로 영상은 400 + PORTRAIT_NOT_SUPPORTED.
    with open("samples/test_portrait_1080x1920.mp4", "rb") as f:
        response = client.post(
            "/api/upload",
            files={"video": ("portrait.mp4", f, "video/mp4")},
        )
    assert response.status_code == 400
    body = response.json()
    assert body["detail"]["error_code"] == "PORTRAIT_NOT_SUPPORTED"
    assert "가로" in body["detail"]["message_ko"]

def test_analysis_response_includes_confidence(monkeypatch):
    # 완료된 분석 응답에 confidence/warnings 가 포함되는지.
    # (실제 영상으로 통합 테스트 또는 ANALYSIS_STATUS 를 직접 채워서 호출)
    ...

def test_member_creation():
    response = client.post("/api/members", json={
        "name": "홍길동",
        "trainer_id": "trainer-uuid",
    })
    assert response.status_code == 200
    assert response.json()["name"] == "홍길동"
```

---

## 🧪 검증 방법

### 1단계: 서버 실행
```bash
cd server
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
# http://localhost:8000/docs 접속해서 OpenAPI 문서 확인
```

### 2단계: curl로 end-to-end 테스트
```bash
# 1. 영상 업로드
curl -X POST http://localhost:8000/api/upload \
  -F "video=@samples/test_run_10s.mp4"
# → {"analysis_id": "abc-123", "status": "processing", ...}

# 2. 30초 대기 후 결과 조회
sleep 30
curl http://localhost:8000/api/analysis/abc-123 | jq

# 3. 렌더링 영상 다운로드
curl http://localhost:8000/storage/renders/abc-123.mp4 -o result.mp4

# 4. 회원 등록
curl -X POST http://localhost:8000/api/members \
  -H "Content-Type: application/json" \
  -d '{"name":"홍길동","trainer_id":"trainer-1"}'

# 5. 회원별 히스토리 조회
curl http://localhost:8000/api/members/{member_id}/history | jq
```

### 3단계: 외부 디바이스에서 호출 (필수!)
```bash
# PC의 로컬 IP 확인 (예: 192.168.1.100)
ipconfig getifaddr en0  # macOS
ip addr show            # Linux

# 같은 WiFi의 다른 기기(폰/노트북)에서
curl http://192.168.1.100:8000/health
# → 정상 응답이 와야 Step 5(앱) 진행 가능

# 방화벽 차단 시 macOS:
# 시스템 환경설정 → 보안 → 방화벽 → uvicorn 허용
# Linux:
sudo ufw allow 8000
```

### 4단계: 동시 요청 처리 검증
```bash
# 3개 분석을 동시에 시작
for i in {1..3}; do
  curl -X POST http://localhost:8000/api/upload \
    -F "video=@samples/test_run_3s.mp4" &
done
wait

# 각각 모두 다른 analysis_id 받고 완료되는지 확인
```

---

## 💬 추천 Vibe Coding 명령

```
1. "PRD-4-api.md를 보고 server/main.py 작성. FastAPI 앱, CORS, StaticFiles, 라우터 통합."

2. "server/api/upload.py 구현. UploadFile로 영상 받고 BackgroundTasks로 분석 시작. 진행 상태는 인메모리 dict 사용."

3. "server/api/analysis.py에 GET /api/analysis/{id} 구현. processing/completed/failed 상태별 응답 분기."

4. "server/api/members.py에 회원 CRUD + 히스토리 조회 엔드포인트 구현. trainer_id로 권한 분리."

5. "server/tests/test_api.py 작성. TestClient로 모든 엔드포인트 검증."

6. "uvicorn으로 0.0.0.0:8000 실행하고 curl로 end-to-end 동작 확인하는 통합 테스트 스크립트 작성."

7. "방화벽 설정 안내문 + 로컬 IP 확인 명령을 README.md에 추가."
```

---

## 📤 산출물

### 생성될 파일
```
server/
├── main.py
├── requirements.txt                  # (업데이트)
├── api/
│   ├── __init__.py
│   ├── upload.py
│   ├── analysis.py
│   └── members.py
├── storage/
│   ├── uploads/
│   ├── renders/
│   ├── reports/
│   └── state.json (자동 생성)
└── tests/
    └── test_api.py
```

### 다음 단계로 넘길 인터페이스

**Step 5(앱 촬영·업로드)가 사용할 API**:

| Method | Endpoint | 용도 |
|---|---|---|
| POST | `/api/upload` | 영상 업로드 + 분석 시작 |
| GET | `/api/analysis/{id}` | 분석 결과 폴링 |
| POST | `/api/members` | 회원 등록 (트레이너 모드) |
| GET | `/api/members?trainer_id=...` | 회원 목록 |
| GET | `/api/members/{id}/history` | 회원 누적 히스토리 |
| GET | `/storage/renders/{id}.mp4` | 렌더링 영상 다운로드 |
| GET | `/storage/reports/{id}.csv` | CSV 리포트 다운로드 |

**BASE_URL**: `http://<PC_LOCAL_IP>:8000`

**`GET /api/analysis/{id}` 완료 응답 스키마** (PRD-8 반영):

```jsonc
{
  "analysis_id": "abc-123",
  "status": "completed",
  "rendered_video_url": "/storage/renders/abc-123.mp4",
  "csv_url": "/storage/reports/abc-123.csv",
  "summary": { "total_strikes": 19, "cadence_spm": 157.6, "fps": 30.0, ... },
  "metrics": { ... },
  "asymmetry": { ... },
  "danger_timestamps": [ ... ],
  "coach_message_ko": "...",
  "confidence": "high",                    // PRD-8: "high" | "medium" | "low"
  "warnings": [                            // PRD-8: 빈 배열일 수 있음
    { "code": "HIGH_CADENCE_LOW_FPS", "message_ko": "..." }
  ]
}
```

---

## ⚠️ 흔한 함정

1. **`host="0.0.0.0"` 필수**
   - `127.0.0.1`로 띄우면 외부 디바이스 접근 불가
   - 반드시 `--host 0.0.0.0`

2. **방화벽이 8000 포트 차단**
   - macOS: 시스템 환경설정 → 보안 → 방화벽 허용
   - Windows: Windows Defender 방화벽 → 인바운드 규칙
   - Linux: `sudo ufw allow 8000`

3. **CORS 에러**
   - 모바일 앱에서 호출 시 CORS preflight 실패 가능
   - 프로젝트 단계에서는 `allow_origins=["*"]` 허용

4. **BackgroundTasks의 한계**
   - FastAPI BackgroundTasks는 동일 프로세스에서 실행
   - 분석 작업이 무거우면 메인 응답이 지연될 수 있음
   - Phase 2에서는 Celery + Redis로 전환 권장

5. **인메모리 저장의 위험**
   - 서버 재시작 시 분석 결과 손실
   - 영상 파일은 디스크에 남지만 분석 메타데이터는 사라짐
   - 최소한 `state.json` 백업 필수

6. **영상 파일 크기 제한**
   - FastAPI 기본 multipart 제한 확인
   - 큰 영상 업로드 시 `client_max_body_size` 설정 (uvicorn은 기본적으로 무제한)

7. **분석 진행률 표시**
   - 현재 API는 processing/completed만 반환
   - 향후 0~100% 진행률 추가 시 WebSocket 또는 SSE 고려

8. **PRD-8 검증 실패 응답 포맷 통일** _(2026-05-15)_
   - FastAPI `HTTPException(detail=str)` 으로 던지면 `{"detail": "메시지"}` 가 되어 클라이언트가 `error_code` 를 파싱할 수 없음
   - 반드시 `HTTPException(detail={"error_code": ..., "message_ko": ...})` 딕셔너리 형태로 던질 것
   - 응답은 `{"detail": {"error_code": "FPS_TOO_LOW", "message_ko": "..."}}` 가 됨

9. **거부된 영상 디스크 정리**
   - 업로드 직후 validate 실패 시 디스크에 남긴 영상은 즉시 `os.remove()` 로 정리
   - 안 그러면 `storage/uploads/` 가 거부된 영상으로 가득 참

10. **`run_full_analysis_with_output` 존재 시점** _(2026-05-16 갱신)_
    - PRD-3 완료 시점부터 `analyzer/__init__.py` 에 `run_full_analysis_with_output(video_path, output_dir) → dict` 가 존재
    - API 레이어(`api/upload.py`)는 이 통합 함수를 직접 호출하여 분석 + 렌더링 + CSV + 코칭을 한 번에 받음 (별도 결합 불필요)
    - 시그니처: `{"analysis_result": AnalysisResult, "rendered_video_path": str, "csv_report_path": str, "coach_message": str}`
    - PRD-7 raw_df 캐싱 (2026-05-16) 이후 두 public 진입점이 `_analyze_from_raw_df` private helper 를 공유 — 외부 시그니처는 불변
