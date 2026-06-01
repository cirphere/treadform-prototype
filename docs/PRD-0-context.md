# PRD-0: 프로젝트 공통 컨텍스트

> ⚠️ **이 파일은 모든 단계(Step 1~7)에서 항상 참조됩니다.**
> Claude Code 세션 시작 시 가장 먼저 읽어야 할 컨텍스트 문서입니다.

---

## 🎯 프로젝트 한 줄 요약

스마트폰 앱으로 트레드밀 측면 러닝 영상을 촬영·업로드하면, 로컬 PC FastAPI 서버가 MediaPipe Pose로 후처리 분석하여 **부상 방지 3대 지표**를 한국어 피드백으로 반환하는 **B2B 트레이너 + B2C 일반 사용자 듀얼 모드 솔루션**.

---

## 🔒 1. 절대 준수 제약 사항

| 항목 | 값 | 이유 |
|---|---|---|
| AI 모델 | **MediaPipe Pose (BlazePose)** | HEEL/FOOT_INDEX 좌표 포함, CPU 최적화 |
| `model_complexity` | **2 (Heavy)** | 후처리이므로 정확도 우선 |
| 처리 방식 | **후처리 (Post-processing)** | 실시간 X, 모든 프레임 100% 분석 |
| 분석 환경 | **로컬 PC CPU** | GPU 의존 X, 클라우드 X |
| 앱↔서버 통신 | **동일 WiFi LAN HTTP POST** | 외부망 X |
| 영상 해상도 | **앱에서 720p로 다운스케일** | 업로드 병목 해소 |
| UI 언어 | **한국어 100%** | 핵심 차별점 |
| 운동 환경 | **실내 트레드밀 전용** | 야외 X (변수 통제) |
| 상태 색상 | **🔴 Danger / 🟡 Warning / 🟢 Safe** | 3단계 고정 |

### ⚠️ 절대 금지 사항
- RTMPose, MoveNet 등 다른 모델 사용 금지 (HEEL 좌표 없음)
- `model_complexity=0` 또는 `1` 사용 금지
- 실시간 스트리밍 처리 금지
- 영문 UI 단독 사용 금지
- 코드 내 매직 넘버 금지 (모든 임계값은 `config.py`)

---

## 🎁 2. 4대 차별화 전략 (잊지 말 것)

1. **100% 한국어 현지화** — UI, 리포트, AI 코칭 메시지
2. **트레이너 모드 토글** — 한 앱에서 B2C ↔ B2B 전환
3. **직관성 우선** — 15+ 메트릭 X, 3대 지표 + 🔴🟡🟢 색상
4. **트레드밀 환경 특화** — AR 가이드라인으로 표준화된 구도

---

## 🏗️ 3. 시스템 아키텍처

```
┌─────────────────────────────────────────────────────┐
│  [Mobile App] React Native / Flutter                │
│  - AR 가이드라인 오버레이 촬영                       │
│  - 720p 다운스케일 + 압축                            │
│  - 결과 영상 인앱 재생 (슬로우 모션)                 │
│  - 누적 대시보드 + 트레이너 모드 토글                │
└────────────────────┬────────────────────────────────┘
                     │ HTTP POST (multipart/form-data)
                     │ WiFi LAN
                     ▼
┌─────────────────────────────────────────────────────┐
│  [Local PC Server] FastAPI + MediaPipe              │
│  - 영상 수신/저장 + 입력 사양 검증 (PRD-8)           │
│  - MediaPipe Pose Tasks API (heavy, complexity=2)    │
│  - 5단계 전처리: mask → Hampel → L/R 보정            │
│                  → forward fill → One Euro Filter    │
│  - 좌/우 발목 독립 추적 + 쿨다운                     │
│  - 3대 지표 연산 → 한국어 코칭 생성                  │
│  - 신뢰도/경고 (PRD-8) + 렌더링 영상 + JSON + CSV    │
└────────────────────┬────────────────────────────────┘
                     │ HTTP Response (영상 URL + JSON)
                     ▼
                  [Mobile App]
```

---

## 📁 4. 전체 프로젝트 디렉토리 구조

```
treadform/
├── PRD-0-context.md                 # 이 파일 (항상 참조)
├── PRD-1-pose-pipeline.md           # Step 1
├── PRD-2-metrics.md                 # Step 2
├── PRD-3-render-coach.md            # Step 3
├── PRD-4-api.md                     # Step 4
├── PRD-5-app-capture.md             # Step 5
├── PRD-6-app-result.md              # Step 6
├── PRD-7-integration.md             # Step 7
├── PRD-8-video-input-spec.md        # 입력 영상 사양 & 검증 (cross-cut)
├── README.md
│
├── server/                          # FastAPI 백엔드
│   ├── main.py                      # (PRD-4) FastAPI 엔트리포인트
│   ├── config.py                    # 모든 임계값 상수
│   ├── requirements.txt
│   │
│   ├── run_analysis.py              # 개발 도구: CLI 분석 실행기
│   ├── debug_overlay.py             # 개발 도구: 스켈레톤 디버그 영상 생성
│   ├── analyze_spikes.py            # 개발 도구: 전처리 spike/lag 분석
│   │
│   ├── api/                         # (PRD-4) REST 라우터
│   │   ├── upload.py
│   │   ├── analysis.py
│   │   └── members.py
│   │
│   ├── video_validator.py           # PRD-8: 하드 요건 검증
│   ├── analyzer/
│   │   ├── pose_extractor.py        # Tasks API (PoseLandmarker)
│   │   ├── filters.py               # One Euro Filter
│   │   ├── preprocessor.py          # 5단계 파이프라인
│   │   ├── foot_strike_detector.py
│   │   ├── quality_assessor.py      # PRD-8: 소프트 경고/신뢰도
│   │   ├── renderer.py              # (PRD-3) 스켈레톤 오버레이
│   │   ├── coach_message.py         # (PRD-3) 한국어 코칭 메시지
│   │   └── metrics/
│   │       ├── knee_flexion.py
│   │       ├── foot_strike.py
│   │       ├── overstriding.py
│   │       ├── vertical_osc.py
│   │       └── asymmetry.py
│   │
│   ├── models/                      # Pydantic 스키마
│   ├── .models/                     # mediapipe heavy.task 자동 캐시 (gitignored)
│   ├── storage/
│   │   ├── uploads/
│   │   ├── renders/
│   │   └── reports/
│   └── tests/
│
└── app/                             # React Native (or Flutter)
    ├── package.json
    ├── App.tsx
    └── src/
        ├── screens/
        ├── components/
        ├── services/
        ├── context/
        └── i18n/
```

---

## 🎨 5. 색상 코딩 (전역 상수)

```python
# Python (OpenCV는 BGR 순서!)
COLOR_SAFE_BGR    = (94, 197, 34)    # #22C55E
COLOR_WARNING_BGR = (8, 179, 234)    # #EAB308
COLOR_DANGER_BGR  = (68, 68, 239)    # #EF4444
```

```typescript
// TypeScript (앱 - RGB)
export const COLORS = {
  SAFE: '#22C55E',      // 🟢
  WARNING: '#EAB308',   // 🟡
  DANGER: '#EF4444',    // 🔴
} as const;
```

---

## 📐 6. Vibe Coding 절대 원칙

1. **임계값은 항상 `config.py`에서만** — 매직 넘버 금지
2. **MediaPipe landmark는 enum 사용** — `analyzer.pose_extractor.PoseLandmark.LEFT_HIP` (legacy `mp.solutions` 는 v0.10.35 부터 제거됨 → Tasks API + 자체 정의 IntEnum), 숫자 인덱스 금지
3. **모든 함수에 docstring 필수** — 한국어 또는 영어 일관성 유지
4. **로깅은 `logging` 모듈** — `print` 금지
5. **테스트 없는 기능은 머지 금지** — pytest 통과 필수
6. **단계별 산출물 검증 후 다음 단계로** — Definition of Done 체크리스트 준수

---

## 🗺️ 7. 단계별 흐름도

```
Step 0 (이 파일) ─→ 항상 참조
  ↓
Step 1: Pose 추출 & 전처리      → keypoints DataFrame
  ↓
Step 2: 3대 지표 계산            → 지표 + 상태 판정 JSON
  ↓
Step 3: 렌더링 & 코칭            → 렌더링 영상 + CSV + 한국어 메시지
  ↓
Step 4: FastAPI 엔드포인트       → WiFi LAN 호출 가능한 서버
  ↓
Step 5: 앱 촬영 & 업로드         → 영상 캡처 → 서버 업로드
  ↓
Step 6: 앱 결과 표시 & 대시보드  → end-to-end 사용자 플로우
  ↓
Step 7: 통합 테스트 & 벤치마크   → 시연 가능한 MVP
```

---

## 📚 8. 핵심 용어 정의

| 약어/용어 | 의미 |
|---|---|
| **Foot Strike** | 발이 트레드밀에 닿는 순간 (착지 시점) |
| **Stride** | 동일 발의 연속 착지 간격 (예: 왼발→왼발) |
| **Step** | 좌우 교차 착지 간격 (예: 왼발→오른발) |
| **Local Minima** | 시계열의 극소점 (발목 Y 최소 = 착지) |
| **Cooldown** | 동일 착지 중복 판정 방지를 위한 최소 프레임 간격 |
| **Occlusion** | 신체 가림으로 인식 불가 현상 |
| **Jitter** | 프레임 간 미세한 인식 오차로 인한 좌표 흔들림 |
| **Knee Flexion** | 무릎 굴곡 각도 (관절 안쪽 각도) |
| **Overstriding** | 무게중심 대비 발이 너무 앞에 착지하는 현상 |
| **Vertical Oscillation** | 골반 상하 진폭 (낭비 에너지 지표) |

---

## 🔧 9. 공통 개발 환경

### 서버 (Python)
- Python 3.10+
- 가상환경: `python -m venv venv`
- 주요 패키지: `fastapi`, `uvicorn`, `mediapipe>=0.10.35` (Tasks API), `opencv-python`, `numpy`, `scipy`, `pandas`, `pydantic`
- mediapipe heavy 모델 (`pose_landmarker_heavy.task`, ~30MB) 은 첫 실행 시 자동 다운로드되어 `server/.models/` 에 캐시

### 앱
- **React Native** 권장 (또는 Flutter)
- 동일 WiFi LAN 필수
- `BASE_URL = "http://<PC_LOCAL_IP>:8000"` 환경변수 설정

---

## 📌 10. 이 문서의 사용 방법

각 Step PRD 파일 작업 시작 시 다음과 같이 호출:

```bash
# Claude Code 세션 시작
claude

# 첫 명령으로 컨텍스트 + 해당 단계 PRD 동시 참조
"PRD-0-context.md를 먼저 읽고, PRD-1-pose-pipeline.md의 모든 작업을 진행해줘"
```

또는 Claude Code의 `CLAUDE.md` 자동 컨텍스트 기능을 활용하려면 이 파일을 `CLAUDE.md`로 심볼릭 링크하거나 복사:

```bash
ln -s PRD-0-context.md CLAUDE.md
```

---

## 🎯 11. 최종 목표 (MVP 완성 조건)

- [ ] 트레드밀 측면 촬영 영상을 앱에서 업로드 가능
- [ ] 서버가 60초 이내 분석 완료
- [ ] 3대 지표 + 좌/우 비대칭 측정 정확
- [ ] 스켈레톤 오버레이 영상 + Danger 마커 표시
- [ ] 한국어 코칭 메시지 자연스러움
- [ ] 트레이너 모드 토글 동작
- [ ] 회원별 비포/애프터 그래프 출력
- [ ] WiFi LAN에서 안정적 동작
