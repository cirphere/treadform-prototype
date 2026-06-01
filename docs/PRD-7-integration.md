# PRD-7: 통합 테스트 & 벤치마크

> 📍 항상 함께 참조: **[PRD-0-context.md](./PRD-0-context.md)**
> 📍 이전 단계 산출물: **[PRD-6-app-result.md](./PRD-6-app-result.md)**
> 📍 교차 참조: **[PRD-8-video-input-spec.md](./PRD-8-video-input-spec.md)** (거부 시나리오, 신뢰도 시나리오)

---

## 🎯 이 단계의 목표

Step 1~6 + PRD-8 에서 만든 모든 컴포넌트를 **end-to-end로 통합 테스트**하고, **분석 소요 시간 벤치마크**를 측정하여 시연 가능한 MVP로 완성한다. 발견된 이슈를 해결하고 `BENCHMARK.md`, `README.md`를 작성한다.

---

## 📥 입력 (의존성)

- **이전 단계 산출물**: Step 1~6 + PRD-8 의 모든 모듈
- **필수 참조**: 모든 이전 PRD 파일 (PRD-0~8)

---

## ✅ 완료 조건 (Definition of Done)

- [ ] E2E 통합 테스트 시나리오 **7종** 모두 통과 (기존 5 + PRD-8 의 거부 + 저신뢰도)
- [ ] 분석 소요 시간 벤치마크 측정 완료 (목표: 60초 이내, validate() 50ms 포함)
- [ ] `BENCHMARK.md` 작성 (PC 스펙별 처리 시간 + PRD-8 검증 비용 항목)
- [ ] `README.md` 작성 (설치/실행 가이드, mediapipe>=0.10.35)
- [ ] 트레이너 모드 ↔ 일반 모드 전환 무결성 확인
- [ ] 회원 1명당 3회 이상 누적 데이터로 대시보드 검증
- [ ] WiFi LAN 통신 안정성 (재연결, 끊김 처리)
- [ ] **PRD-8 거부 영상 6종에 대해 모두 정확한 `error_code` + 한국어 메시지 반환**
- [ ] **PRD-8 신뢰도 등급별 UI 전환** (high/medium/low) 시각 검증
- [ ] 발견된 버그 모두 수정 또는 KNOWN_ISSUES.md 기록
- [ ] 시연 영상 1분 분량 녹화

---

## 📋 작업 항목

### 1. E2E 통합 테스트 시나리오

#### 시나리오 1: 일반 사용자 단독 사용
```
사전 조건: 모드 OFF, 회원 미선택
플로우:
  1. 앱 시작 → HomeScreen
  2. "촬영 시작" 탭
  3. AR 가이드라인 보고 자세 정렬
  4. 10초 녹화
  5. 720p 변환 (약 5초 대기)
  6. 서버 업로드 (진행률 표시)
  7. 분석 완료까지 폴링 (약 30초)
  8. ResultScreen에서 영상 + 코칭 + 메트릭 확인
  9. Danger 구간 진입 시 자동 0.5x 슬로우 모션 확인

검증 포인트:
  - 모든 화면 한국어 표시
  - 영상 정상 재생
  - 색상 뱃지 정확
  - 코칭 메시지 자연스러움
```

#### 시나리오 2: 트레이너의 신규 회원 등록 및 첫 분석
```
사전 조건: 트레이너 모드 ON
플로우:
  1. ModeToggle ON
  2. "회원 추가" → "홍길동" 입력 → 등록
  3. 회원 선택
  4. 촬영 → 업로드 (member_id 자동 포함)
  5. 분석 결과 확인
  6. 회원의 누적 데이터에 1회 기록되는지 확인

검증 포인트:
  - member_id가 API 요청에 포함됨
  - 서버의 MEMBER_HISTORY에 저장됨
  - DashboardScreen에서 1회 데이터 표시
```

#### 시나리오 3: 트레이너의 회원 누적 데이터 시각화
```
사전 조건: 동일 회원으로 3회 이상 분석 완료
플로우:
  1. 회원 선택
  2. DashboardScreen 진입
  3. 3개 그래프 모두 표시 확인
  4. 시간 순서로 추이 정확한지 확인
  5. PT 효과 요약 텍스트 확인

검증 포인트:
  - 그래프 X축이 시간순 정렬
  - 데이터 포인트 누락 없음
  - "Heel Strike 15회 → 3회" 형태 자동 산출
```

#### 시나리오 4: 모드 전환 무결성
```
플로우:
  1. 트레이너 모드 ON → 회원 A 선택 → 분석
  2. 모드 OFF (일반)
  3. 본인 분석 (member_id 없이)
  4. 모드 ON → 회원 B 선택 → 분석
  5. 회원 A의 데이터에 B의 결과가 섞이지 않는지 확인

검증 포인트:
  - AsyncStorage 상태 정확히 영속화
  - 회원 데이터 격리
```

#### 시나리오 5: 네트워크 장애 복구
```
플로우:
  1. 촬영 후 업로드 직전 WiFi OFF
  2. 업로드 실패 메시지 확인
  3. WiFi 재연결 후 재시도 버튼 동작
  4. 분석 중 WiFi 끊김 → 폴링 실패 → 재연결 시 폴링 재개

검증 포인트:
  - 적절한 에러 메시지 표시 (한국어)
  - 앱 크래시 없음
  - 재시도 시 정상 동작
```

#### 시나리오 6: 거부 영상 처리 (PRD-8)

```
사전 조건: 거부 대상 영상 샘플 6종 준비
  - portrait_1080x1920.mp4    (PORTRAIT_NOT_SUPPORTED)
  - landscape_640x480.mp4     (RESOLUTION_TOO_LOW)
  - landscape_24fps.mp4       (FPS_TOO_LOW)
  - landscape_3s.mp4          (DURATION_TOO_SHORT)
  - landscape_120s.mp4        (DURATION_TOO_LONG)
  - corrupt.mp4               (CANNOT_OPEN_VIDEO)

플로우:
  1. 각 샘플을 앱 갤러리 업로드 경로로 전송
  2. 서버가 HTTP 400 + error_code 반환 확인
  3. 앱이 i18n 매핑된 한국어 에러를 모달로 표시
  4. "다시 촬영" 버튼으로 CameraScreen 복귀
  5. 거부된 영상이 서버 storage/uploads/ 에 남지 않음

검증 포인트:
  - 각 케이스의 error_code 정확 매핑
  - message_ko 가깨짐 없이 표시
  - mediapipe 호출 비용 발생 X (서버 로그에서 확인)
  - 디스크 정리 완료
```

#### 시나리오 7: 저신뢰도 (low confidence) 결과 UX (PRD-8)

```
사전 조건:
  - 빠른 페이스 30fps 영상 (cadence ≥ 190 spm) → medium 등급
  - 어두운 조명 + 헐렁한 옷 영상 → low 등급 (3개+ 경고)

플로우:
  1. medium 등급 영상 분석 → 신뢰도 배지 노랑("보통") + 경고 카드 1~2건
  2. low 등급 영상 분석 → 신뢰도 배지 빨강("낮음") + 경고 카드 3건+
     + 메트릭/코칭 영역 30% 투명도 + "참고용" 배너
  3. 렌더링 영상 좌상단에도 신뢰도 배지 합성 확인 (PRD-3)
  4. low 영상의 결과를 회원 히스토리에 저장할지 사용자에게 확인 모달

검증 포인트:
  - confidence 등급별 색상/문구 정확
  - warnings[] 가 빈 배열이면 카드 미표시
  - low 등급 시 메트릭이 톤다운돼도 신뢰도 배지/경고 카드는 또렷이 보임
  - PT 트레이너 모드에서 low 영상이 누적 그래프에 포함될지 정책 결정 필요
```

### 2. 벤치마크 측정

#### 측정 항목

```python
# server/tests/test_benchmark.py
import time
import psutil
import pytest
from analyzer import run_full_analysis_with_output

@pytest.mark.benchmark
def test_analysis_speed_3s_video():
    """3초 영상의 분석 소요 시간 측정."""
    start = time.time()
    cpu_before = psutil.cpu_percent(interval=1)
    mem_before = psutil.virtual_memory().percent

    result = run_full_analysis_with_output(
        video_path="samples/test_run_3s.mp4",
        output_dir="storage/benchmark/",
    )

    elapsed = time.time() - start
    cpu_avg = psutil.cpu_percent(interval=1)
    mem_after = psutil.virtual_memory().percent

    print(f"\n=== 벤치마크 결과 ===")
    print(f"영상 길이: 3초")
    print(f"분석 소요 시간: {elapsed:.2f}초")
    print(f"비율: {elapsed / 3:.1f}배")
    print(f"CPU 평균: {cpu_avg}%")
    print(f"메모리 증가: {mem_after - mem_before}%")

    assert elapsed < 60, f"60초 목표 미달성: {elapsed}초"

@pytest.mark.benchmark
def test_analysis_speed_10s_video():
    """10초 영상 - 실제 사용 시나리오."""
    # 동일 구조
    ...

@pytest.mark.benchmark
def test_concurrent_3_analyses():
    """3개 동시 요청 처리."""
    import concurrent.futures
    start = time.time()
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as exec:
        futures = [
            exec.submit(run_full_analysis_with_output,
                       f"samples/test_run_3s_{i}.mp4",
                       f"storage/benchmark/concurrent_{i}/")
            for i in range(3)
        ]
        results = [f.result() for f in futures]
    elapsed = time.time() - start
    print(f"\n3개 동시 분석: {elapsed:.2f}초")
```

실행:
```bash
pytest tests/test_benchmark.py -v -s -m benchmark
```

### 3. `BENCHMARK.md` 작성

```markdown
# TreadForm 성능 벤치마크

## 테스트 환경

| 항목 | 사양 |
|---|---|
| OS | macOS 14.5 (또는 Windows 11 / Ubuntu 22.04) |
| CPU | Apple M2 Pro 10-core (또는 Intel i7-12700) |
| RAM | 16GB |
| Python | 3.10.13 |
| MediaPipe | ≥ 0.10.35 (Tasks API, heavy 모델 자동 다운로드) |
| model_complexity | 2 (Heavy) |
| 입력 영상 사양 | PRD-8 하드 요건 통과 (가로 ≥ 1280×720, ≥ 30fps, 5~60초) |

## 측정 결과

### 영상 길이별 분석 시간

| 영상 길이 | 분석 시간 | 비율 (영상:분석) |
|---|---|---|
| 3초 | 12.4초 | 1 : 4.1 |
| 5초 | 18.7초 | 1 : 3.7 |
| 10초 | 36.2초 | 1 : 3.6 |
| 15초 | 53.8초 | 1 : 3.6 |

> 목표 (60초 이내) 달성 확인 ✅

### 단계별 소요 시간 (10초 영상 기준)

| 단계 | 소요 시간 | 비율 |
|---|---|---|
| **video_validator.validate (PRD-8)** | **~0.05초** | **0.1%** |
| Pose 추출 (MediaPipe Tasks API heavy) | 28.5초 | 79% |
| 전처리 (5단계: mask → Hampel → L/R → ffill → One Euro) | 0.3초 | 1% |
| 지표 계산 | 0.5초 | 1% |
| **quality_assessor.assess (PRD-8)** | **~0.01초** | **0.03%** |
| 렌더링 (스켈레톤 오버레이) | 6.2초 | 17% |
| CSV 생성 | 0.1초 | 0.3% |
| 기타 | 0.55초 | 1.5% |
| **합계** | **36.2초** | 100% |

### 자원 사용량

| 항목 | 평균 | 최대 |
|---|---|---|
| CPU | 320% (멀티코어) | 580% |
| 메모리 | +850MB | +1.2GB |
| 디스크 I/O | 12MB/s | 45MB/s |

### 동시 처리

| 동시 요청 수 | 평균 처리 시간 | 비고 |
|---|---|---|
| 1개 | 36초 | 단독 |
| 2개 | 52초 | 멀티코어 활용 |
| 3개 | 78초 | CPU 포화 |

## 결론

- ✅ 60초 이내 목표 달성 (10초 영상 기준 36초)
- ⚠️ Pose 추출이 79% 차지 → 최적화 여지
- 💡 동시 2개까지는 안정적, 3개부터는 큐잉 권장

## 향후 최적화 방향

1. MediaPipe GPU 가속 옵션 (CUDA/MPS)
2. 프레임 다운샘플링 (30fps → 15fps)
3. Pose 추출 결과 캐싱
```

### 4. `README.md` 작성

````markdown
# TreadForm

> 한국형 트레드밀 러닝 자세 분석 솔루션 — Vision AI 기반 부상 방지 3대 지표

[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

## 📖 프로젝트 소개

TreadForm은 스마트폰 앱으로 트레드밀 측면 러닝 영상을 촬영·업로드하면 로컬 PC 서버가 MediaPipe Pose로 분석하여 부상 방지 3대 지표를 한국어 피드백으로 제공하는 B2B/B2C 듀얼 모드 솔루션입니다.

## ✨ 핵심 기능

- 🎯 **부상 방지 3대 지표**: 무릎 굴곡 / Foot Strike & Overstriding / Vertical Oscillation
- 🇰🇷 **100% 한국어**: UI, 리포트, AI 코칭 메시지 전체 한국어
- 🔄 **트레이너 모드 토글**: 한 앱으로 PT 코칭 + 개인 사용
- 🎨 **직관적 시각화**: 🔴🟡🟢 색상 + Danger 자동 북마크 + 슬로우 모션
- 📊 **누적 대시보드**: 회원별 비포/애프터 PT 효과 시각화

## 🏗️ 시스템 아키텍처

```
[모바일 앱] → WiFi LAN → [로컬 PC 서버] → MediaPipe Pose 분석 → 결과 반환
```

## 🚀 빠른 시작

### 1. 서버 실행

```bash
cd server
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt

# 외부 디바이스 접근을 위해 host=0.0.0.0 필수
uvicorn main:app --host 0.0.0.0 --port 8000
```

### 2. PC IP 확인

```bash
# macOS
ipconfig getifaddr en0

# Linux
hostname -I

# Windows
ipconfig
```

### 3. 방화벽 설정

- **macOS**: 시스템 환경설정 → 보안 → 방화벽 → uvicorn 허용
- **Windows**: 인바운드 규칙에 8000 포트 추가
- **Linux**: `sudo ufw allow 8000`

### 4. 앱 실행

```bash
cd app
npm install

# src/constants/api.ts의 BASE_URL을 PC IP로 수정
# 예: 'http://192.168.1.100:8000'

# 실기기 빌드 (시뮬레이터는 카메라 미지원)
npx react-native run-ios       # iOS
npx react-native run-android   # Android
```

## 📱 사용 방법

### 일반 사용자
1. 앱 실행 → "촬영 시작"
2. 트레드밀 측면에 폰 거치 → AR 가이드라인 정렬
3. 5~10초 녹화
4. 자동 업로드 → 약 30초 후 결과 확인

### 트레이너 (B2B)
1. 트레이너 모드 토글 ON
2. 회원 등록
3. 회원 선택 후 촬영
4. 누적 분석으로 PT 효과 시각화

## 🛠️ 기술 스택

- **AI 모델**: MediaPipe Pose (BlazePose) Tasks API heavy - model_complexity=2
- **백엔드**: Python 3.10+ + FastAPI + OpenCV + mediapipe ≥ 0.10.35
- **모바일**: React Native + TypeScript
- **분석**: MediaPipe Pose (33 keypoints), 5단계 전처리 (mask → Hampel → L/R 보정 → forward fill → One Euro Filter)
- **입력 검증**: PRD-8 의 video_validator + quality_assessor (confidence/warnings)

## 📊 성능

- 분석 소요 시간: 약 30초 (10초 영상 기준)
- 자세한 벤치마크: [BENCHMARK.md](./BENCHMARK.md)

## 📚 문서

| 문서 | 내용 |
|---|---|
| `PRD-0-context.md` | 프로젝트 공통 컨텍스트 |
| `PRD-1-pose-pipeline.md` | Pose 추출 및 전처리 |
| `PRD-2-metrics.md` | 3대 지표 계산 |
| `PRD-3-render-coach.md` | 렌더링 및 코칭 메시지 |
| `PRD-4-api.md` | FastAPI 엔드포인트 |
| `PRD-5-app-capture.md` | 앱 촬영 및 업로드 |
| `PRD-6-app-result.md` | 앱 결과 표시 및 대시보드 |
| `PRD-7-integration.md` | 통합 테스트 및 벤치마크 |
| `PRD-8-video-input-spec.md` | 입력 영상 사양 & 검증 (cross-cut) |
| `BENCHMARK.md` | 성능 측정 결과 |
| `KNOWN_ISSUES.md` | 알려진 이슈 |

## 🐛 알려진 이슈

[KNOWN_ISSUES.md](./KNOWN_ISSUES.md) 참조

## 📝 라이선스

MIT License (또는 프로젝트 라이선스)

## 👥 팀

WE-Meet Project Team
````

### 5. `KNOWN_ISSUES.md` 작성

```markdown
# 알려진 이슈

## 🔴 Critical

(현재 없음)

## 🟡 Warnings

### W-001: 동시 3개 이상 분석 시 CPU 포화
- **증상**: 4번째 요청부터 처리 시간이 급격히 증가
- **원인**: MediaPipe Pose가 CPU 멀티코어를 최대 활용
- **워크어라운드**: 서버 측 큐잉 (Phase 2에서 Celery 도입)

### W-002: iOS 시뮬레이터에서 카메라 미지원
- **증상**: 시뮬레이터에서 촬영 화면이 검은색
- **원인**: iOS 시뮬레이터의 일반적 제약
- **워크어라운드**: 실기기에서 테스트

### W-003: 빠른 페이스 (4'/km, ≥190 spm) + 30fps 에서 스켈레톤 추적 저하
- **증상**: 다리 스윙 구간에서 mediapipe 가 한 프레임씩 놓치거나 좌/우 혼동
- **원인**: 30fps × 200 spm = 1보당 9프레임. 모션 블러 + 프레임 간 점프
- **워크어라운드 (PRD-8)**: `HIGH_CADENCE_LOW_FPS` 경고 + 60fps 권장 안내
- **근본 해결**: 사용자가 60fps 로 재촬영 (대부분의 최신 스마트폰 지원)

## 🟢 Minor

### M-001: 720p 변환 시 음성 제거됨
- **상태**: 의도된 동작
- **이유**: 음성은 분석에 불필요하며 파일 크기 절약

### M-002: 한글 폰트 자동 탐색이 일부 시스템에서 실패
- **워크어라운드**: 시스템에 NanumGothic 설치 또는 폰트 경로 수동 지정

### M-003: 세로 영상 거부 시 사용자가 "왜 안 되지?" 라고 느낌
- **상태**: 의도된 동작 (PRD-8)
- **이유**: 분석은 측면 횡방향 움직임이 본질 → 가로(16:9) 정합
- **완화**: 촬영 화면 진입 시 captureGuide 모달로 사전 안내 + CameraScreen 가로 강제
```

### 6. 시연 영상 녹화

**1분 시연 시나리오**
- 0:00~0:10 — 앱 소개 + 핵심 기능 화면
- 0:10~0:30 — 일반 사용자 플로우 (촬영 → 결과)
- 0:30~0:50 — 트레이너 모드 (회원 등록 → 분석 → 대시보드)
- 0:50~1:00 — PT 효과 시각화 강조

### 7. 발견된 버그 수정 라운드

```python
# 통합 테스트 중 발견된 버그를 GitHub Issue 또는 별도 파일에 기록
# 각 이슈마다 다음 형식:

ISSUE-001: 영상 업로드 시 한글 파일명 깨짐
  원인: multipart/form-data 인코딩 문제
  수정: filename을 UUID로 강제 변환
  파일: server/api/upload.py

ISSUE-002: 트레이너 모드에서 회원 미선택 상태로 촬영 시 일반 분석으로 처리
  원인: member_id가 None일 때 분기 누락
  수정: 회원 선택 강제 UI 추가
  파일: app/src/screens/HomeScreen.tsx
```

---

## 🧪 검증 방법

### 1단계: 시나리오 5종 수동 테스트
- 각 시나리오마다 체크리스트 작성 후 통과 여부 기록

### 2단계: 자동화된 통합 테스트
```bash
# 서버 단위 + 통합
cd server
pytest -v

# 벤치마크
pytest tests/test_benchmark.py -v -s -m benchmark
```

### 3단계: 실기기 종합 테스트
- iOS 1대 + Android 1대로 동일 시나리오 반복
- 각 디바이스에서 모든 화면이 정상 표시되는지 확인

### 4단계: 시연 리허설
- 시연 영상 녹화 전 3회 이상 리허설
- 끊김, 에러 메시지 없는 부드러운 흐름 확인

---

## 💬 추천 Vibe Coding 명령

```
1. "PRD-7-integration.md의 시나리오 5종 검증용 체크리스트를 INTEGRATION_TEST_CHECKLIST.md로 만들어줘."

2. "server/tests/test_benchmark.py 작성. 3초/10초 영상 분석 시간 측정 + 동시 처리 테스트 포함."

3. "BENCHMARK.md 템플릿 작성. 측정 결과는 빈 칸으로 두고, pytest 실행 후 수동으로 채울 수 있게."

4. "README.md 작성. 빠른 시작 + 방화벽 설정 안내 + 모든 PRD 문서 링크 포함."

5. "KNOWN_ISSUES.md 작성. 통합 테스트 중 발견된 이슈를 단계별 우선순위로 정리."

6. "통합 테스트 시나리오 1~5 실행 스크립트 작성. 가능한 부분은 자동화, 수동 검증 부분은 명시."

7. "시연 영상 녹화 가이드 작성. 화면 캡처 도구 권장, 1분 분량의 스크립트 포함."
```

---

## 📤 산출물

### 생성될 파일
```
/
├── README.md
├── BENCHMARK.md
├── KNOWN_ISSUES.md
├── INTEGRATION_TEST_CHECKLIST.md
└── server/tests/
    └── test_benchmark.py
```

### 최종 MVP 완성 체크리스트

- [ ] 서버: FastAPI + MediaPipe + 3대 지표 + 한국어 코칭 + 렌더링
- [ ] 앱: 촬영 + 720p 변환 + 업로드 + 폴링 + 결과 + 대시보드
- [ ] 한국어: 모든 UI/메시지/리포트
- [ ] 트레이너 모드: 토글 + 회원 관리 + 누적 대시보드
- [ ] 직관성: 🔴🟡🟢 색상 + Danger 자동 북마크 + 0.5x 슬로우 모션
- [ ] 트레드밀 특화: AR 가이드라인
- [ ] 분석 시간: 60초 이내
- [ ] 시연 영상: 1분 분량

---

## ⚠️ 흔한 함정

1. **벤치마크 측정 환경 일관성**
   - 다른 프로세스가 CPU 점유 시 결과 왜곡
   - 측정 전 다른 무거운 앱 종료
   - 가능하면 동일 환경에서 3회 측정 후 평균

2. **시연 시 라이브 분석의 위험**
   - 실시간 분석은 네트워크/CPU 변동으로 실패 가능
   - 시연용 사전 분석 데이터를 캐시해두고 보여주는 백업 준비

3. **WiFi 환경 차이**
   - 발표장의 WiFi가 분리 격리(Client Isolation) 켜져 있으면 통신 불가
   - 핫스팟 또는 직접 라우터 지참 권장

4. **앱 빌드 시간**
   - iOS Release 빌드: 15~30분
   - Android Release: 5~10분
   - 시연 직전 빌드 금지, 미리 빌드 후 테스트

5. **저장 공간**
   - 분석 누적 시 영상이 수십 GB 차지
   - 시연 전 `storage/uploads/`, `storage/renders/` 정리

6. **버전 관리**
   - 다양한 PRD 단계 작업 후 git에 모든 변경사항 커밋
   - 시연 전 안정 버전 태깅 (`git tag v1.0-mvp`)

7. **시연용 샘플 영상 준비**
   - 좋은 자세 영상 1개 (대부분 🟢, confidence=high)
   - 나쁜 자세 영상 1개 (Heel Strike 우세)
   - 누적 데이터용 동일 인물 3회 영상 (개선되는 추세)
   - **PRD-8 거부 시나리오용 6종** (portrait/low-res/low-fps/short/long/corrupt)
   - **medium/low confidence 영상** 각 1개 (빠른 페이스 / 어두운 조명)

8. **PRD-8 거부 영상 6종 사전 준비** _(2026-05-16 갱신)_
   - `server/tests/test_video_rejection_e2e.py` 가 cv2.VideoWriter 로 6종을 자동 합성하여 `server/tests/reject_samples/` 에 캐시한다 (session-scoped fixture).
     - portrait_720x1280.mp4 / low_res_640x480.mp4 / low_fps_24fps.mp4 / duration_3s.mp4 / duration_65s.mp4 / corrupt.mp4
   - 실행: `venv\Scripts\python -m pytest tests\test_video_rejection_e2e.py -v` → 6 passed.
   - 합성된 mp4 는 그대로 앱 수동 검증 (시나리오 6) 에 `adb push` 로 활용 가능 — ffmpeg 의존성 없음. 호스트에 ffmpeg 이 없는 환경에서도 동작.

9. **벤치마크 시 validate 비용 무시 가능 확인** _(PRD-8)_
   - 0.05초 / 36초 = 0.14% — 무시 가능
   - 단, ffprobe 사용 시 외부 프로세스 호출이라 더 느릴 수 있음 → cv2 만 사용

10. **신뢰도 등급별 시연 데모 흐름**
    - high 등급으로 메인 시연
    - 의도적으로 빠른 페이스 영상을 medium 등급 보너스로 시연 → "이런 경고도 잡아냅니다"
    - low 등급은 시연 영상에서 제외 (UX 떨어짐)
