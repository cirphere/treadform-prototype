# TreadForm

> 한국형 트레드밀 러닝 자세 분석 솔루션 — MediaPipe Pose 기반 부상 방지 3대 지표 + 한국어 코칭

## 프로젝트 소개

TreadForm 은 스마트폰 앱으로 트레드밀 측면 러닝 영상을 촬영·업로드하면 로컬 PC 서버가 MediaPipe Pose 로 분석하여 부상 방지 3대 지표를 한국어 피드백으로 제공하는 B2C/B2B 듀얼 모드 솔루션이다.

## 핵심 기능

- **부상 방지 3대 지표**: 무릎 굴곡 / Foot Strike & Overstriding / Vertical Oscillation
- **100% 한국어 UI · 리포트 · AI 코칭**
- **트레이너 모드 토글**: 한 앱으로 PT 코칭 + 개인 사용
- **직관적 시각화**: 색상 배지 + Danger 자동 북마크 + 0.5x 슬로우 모션
- **누적 대시보드**: 회원별 비포/애프터 PT 효과 시각화
- **입력 영상 자동 검증**: 해상도/fps/길이/세로방향 거부 (PRD-8)
- **신뢰도 등급 (high/medium/low)**: 빠른 페이스 + 저fps 등 분석 한계 자동 안내

## 시스템 아키텍처

```
[모바일 앱 (RN)] → WiFi LAN/Loopback → [로컬 PC 서버 (FastAPI)]
                                       → MediaPipe Pose (33 keypoints)
                                       → 5단계 전처리 (mask → Hampel → L/R → ffill → One Euro)
                                       → 3대 지표 + 코칭 + 렌더링 + CSV
```

## 빠른 시작

### 1. 서버 실행

```powershell
Set-Location server
python -m venv venv
venv\Scripts\Activate.ps1
pip install -r requirements.txt

# 외부 디바이스 접근을 위해 host=0.0.0.0 필수
venv\Scripts\python -m uvicorn main:app --host 0.0.0.0 --port 8000
```

### 2. PC IP 확인

```powershell
ipconfig | Select-String "IPv4"
```

서버 PC 의 LAN IP (예: `192.168.0.11`) 를 메모.

### 3. 방화벽 설정

- **Windows**: Defender 방화벽 → 인바운드 규칙 → 새 규칙 → 포트 → TCP 8000 허용
- **macOS**: 시스템 환경설정 → 보안 → 방화벽 → uvicorn 허용
- **Linux**: `sudo ufw allow 8000`

### 4. 앱 실행 (Android)

```powershell
Set-Location app
npm install

# src/constants/api.ts 의 BASE_URL 확인:
#   - 에뮬레이터 dev: 10.0.2.2:8000 (자동)
#   - 실기기 dev: PC LAN IP 수정
npm start              # 별도 터미널: Metro
npm run android        # 또는: Set-Location android; .\gradlew.bat app:installDebug
```

### 5. 분석 실행

1. 앱 시작 → 회원 모드 토글 (선택)
2. "촬영 시작" 또는 "기존 영상 업로드"
3. 5~60초 가로 (1280×720+) 영상 선택
4. 업로드 → 폴링 → ResultScreen 에서 영상 + 메트릭 + 코칭 확인

## 디렉토리 구조

```
vibeRun/
├── README.md                # 본 파일
├── docs/                    # 모든 프로젝트 문서
│   ├── PRD-0~8.md           # 단계별 PRD
│   ├── BENCHMARK.md         # 성능 측정 결과
│   ├── REFERENCES.md        # 학술 참고문헌 (1차 검증된 13종)
│   ├── KNOWN_ISSUES.md      # 알려진 이슈
│   └── INTEGRATION_TEST_CHECKLIST.md  # 7종 E2E 시나리오
├── server/                  # FastAPI + MediaPipe Pose 분석
│   ├── main.py
│   ├── api/                 # upload / analysis / members
│   ├── analyzer/            # pose_extractor / preprocessor / metrics / renderer / coach
│   ├── models/
│   ├── video_validator.py   # PRD-8 하드 요건 검증
│   └── tests/               # 165 테스트 (161 단위 + 4 벤치마크)
└── app/                     # React Native 0.85.3 + TypeScript
    ├── src/
    │   ├── screens/         # Home / Camera / Upload / Processing / Result / Dashboard / MemberSelect
    │   ├── components/      # ConfidenceBadge / WarningList / CoachMessageCard / MetricsSummary / VideoPlayerWithMarkers / ProgressChart
    │   ├── services/        # api / storage / videoPicker
    │   ├── context/         # ModeContext (트레이너 모드)
    │   ├── i18n/            # ko.json
    │   └── constants/       # api / colors
    └── App.tsx              # NavigationContainer + Stack
```

## 기술 스택

| 영역 | 스택 |
|---|---|
| AI 모델 | MediaPipe Pose Tasks API (BlazePose), model_complexity=2 (Heavy) |
| 백엔드 | Python 3.10+ / FastAPI / OpenCV 4.x / mediapipe ≥ 0.10.35 |
| 모바일 | React Native 0.85.3 + TypeScript + new architecture (Fabric) |
| 네비 | @react-navigation v7 (native-stack) |
| 카메라 | react-native-vision-camera v4.7 + orientation-locker |
| 영상 재생 | react-native-video v6.19 |
| 차트 | react-native-chart-kit + SVG |
| 분석 전처리 | 5단계: mask → Hampel → L/R 보정 → forward fill → One Euro Filter |

## 성능

- 분석 소요 시간: 약 30~40초 (10초 60fps 1080p 영상 기준, M-class CPU)
- 자세한 벤치마크: [docs/BENCHMARK.md](./docs/BENCHMARK.md)

## 문서

| 문서 | 내용 |
|---|---|
| [`docs/PRD-0-context.md`](./docs/PRD-0-context.md) | 프로젝트 공통 컨텍스트 |
| [`docs/PRD-1-pose-pipeline.md`](./docs/PRD-1-pose-pipeline.md) | Pose 추출 및 전처리 |
| [`docs/PRD-2-metrics.md`](./docs/PRD-2-metrics.md) | 3대 지표 계산 + 비대칭 |
| [`docs/PRD-3-render-coach.md`](./docs/PRD-3-render-coach.md) | 렌더링 / CSV / 한국어 코칭 |
| [`docs/PRD-4-api.md`](./docs/PRD-4-api.md) | FastAPI 엔드포인트 |
| [`docs/PRD-5-app-capture.md`](./docs/PRD-5-app-capture.md) | 앱 촬영 / 업로드 |
| [`docs/PRD-6-app-result.md`](./docs/PRD-6-app-result.md) | 앱 결과 / 대시보드 |
| [`docs/PRD-7-integration.md`](./docs/PRD-7-integration.md) | 통합 테스트 / 벤치마크 |
| [`docs/PRD-8-video-input-spec.md`](./docs/PRD-8-video-input-spec.md) | 입력 영상 사양 (cross-cut) |
| [`docs/BENCHMARK.md`](./docs/BENCHMARK.md) | 성능 측정 결과 |
| [`docs/REFERENCES.md`](./docs/REFERENCES.md) | 학술 참고문헌 (1차 검증된 13종) |
| [`docs/KNOWN_ISSUES.md`](./docs/KNOWN_ISSUES.md) | 알려진 이슈 |
| [`docs/INTEGRATION_TEST_CHECKLIST.md`](./docs/INTEGRATION_TEST_CHECKLIST.md) | 7종 E2E 시나리오 수동 체크리스트 |

## 알려진 이슈

[docs/KNOWN_ISSUES.md](./docs/KNOWN_ISSUES.md) 참조.

## 라이선스

MIT License.
