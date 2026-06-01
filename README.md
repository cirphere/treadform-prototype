# TreadForm 백엔드 핸드오프 (PRD-1 ~ PRD-3)

> **수신자**: 백엔드 담당
> **범위**: 영상 입력 → 분석 → 산출물(렌더 영상 + 한국어 코칭 + CSV) 생성까지
> **제외**: FastAPI 엔드포인트(PRD-4), 모바일 앱(PRD-5/6), 통합 환경(PRD-7), 운영 데이터

---

## 1. 무엇이 들어있나

이 폴더는 **분석 파이프라인 단독 실행에 필요한 최소 세트**입니다. FastAPI 서버 없이도 `python run_analysis.py` 한 번으로 영상 1개를 끝까지 분석할 수 있습니다.

```
handoff_prd1-3/
├── README.md                            ← 이 문서
├── docs/                                ← PRD 명세 + 참고 자료
│   ├── PRD-0-context.md                 ★ 항상 먼저 읽기 (공통 제약·아키텍처)
│   ├── PRD-1-pose-pipeline.md           Pose 추출 + 5단계 전처리 명세
│   ├── PRD-2-metrics.md                 부상 방지 3대 지표 + 비대칭 명세
│   ├── PRD-3-render-coach.md            렌더 영상 + 한국어 코칭 + CSV 명세
│   ├── PRD-8-video-input-spec.md        입력 검증/품질(신뢰도) 명세
│   ├── REFERENCES.md                    학술 근거 12종
│   ├── BENCHMARK.md                     성능 측정 결과·기준
│   └── KNOWN_ISSUES.md                  현재 알려진 한계·해킹 노트
└── server/
    ├── config.py                        ★ 모든 임계값·튜닝값 (매직 넘버 금지)
    ├── requirements.txt                 Python 의존성
    ├── pytest.ini                       pytest 설정
    ├── run_analysis.py                  CLI 진입점 (단독 실행 스크립트)
    ├── video_validator.py               PRD-8 하드 요건 검증 (해상도/fps/길이)
    ├── pace530.mp4                      테스트용 샘플 영상 (≈8MB, 5:30 pace)
    │
    ├── analyzer/                        ★ 분석 파이프라인 본체
    │   ├── __init__.py                  run_full_analysis / run_full_analysis_with_output
    │   │
    │   │   ── PRD-1: Pose & 전처리 ──
    │   ├── pose_extractor.py            MediaPipe Pose Tasks API (heavy, 33 keypoints)
    │   ├── preprocessor.py              5단계 전처리 (visibility/Hampel/LR-swap/fill/One-Euro)
    │   ├── filters.py                   Hampel + One Euro Filter 구현
    │   ├── foot_strike_detector.py      좌/우 발 독립 추적, 쿨다운 적용한 착지 시점 검출
    │   ├── quality_assessor.py          confidence(high/medium/low) + warnings 산출
    │   │
    │   │   ── PRD-2: 3대 지표 ──
    │   └── metrics/
    │       ├── knee_flexion.py          무릎 굴곡 각도 (Stiff/Borderline/Good/OverBent)
    │       ├── foot_strike.py           착지 유형 (Heel/Mid/Forefoot)
    │       ├── overstriding.py          오버스트라이딩 (Over/Good)
    │       ├── vertical_osc.py          수직 진폭 (High/Good)
    │       └── asymmetry.py             좌우 비대칭 (>10% 경고)
    │
    │       ── PRD-3: 산출물 생성 ──
    │   ├── renderer.py                  3-Layer 스켈레톤 오버레이 MP4 (720p/30fps/H.264)
    │   ├── coach_message.py             우선순위 기반 한국어 코칭 문장 생성
    │   ├── csv_reporter.py              프레임/시간별 모든 지표 CSV 리포트
    │   └── danger_collector.py          위험 타임스탬프 수집(슬로우 모션용)
    │
    ├── models/
    │   └── analysis_result.py           Pydantic AnalysisResult / DangerTimestamp / QualityWarning
    │
    └── tests/                           pytest 단위/통합 테스트
        ├── conftest.py                  sys.path 설정
        ├── test_preprocessor.py         PRD-1 단위 테스트
        ├── test_metrics.py              PRD-2 단위 테스트
        ├── test_renderer.py             PRD-3 렌더 단위 테스트 (mp4 사용)
        ├── test_coach_message.py        PRD-3 코칭 메시지 단위 테스트
        ├── test_csv_reporter.py         PRD-3 CSV 단위 테스트
        ├── test_danger_collector.py     PRD-3 타임스탬프 단위 테스트
        ├── test_quality_assessor.py     PRD-8 신뢰도 단위 테스트
        ├── test_video_validator.py      PRD-8 입력 검증 단위 테스트
        ├── test_video_rejection_e2e.py  PRD-8 거부 시나리오 E2E
        ├── test_benchmark.py            전체 파이프라인 성능 벤치마크
        └── reject_samples/              검증 거부 케이스용 짧은 mp4 6종
```

---

## 2. 일부러 빠진 것 (왜 안 보냈는지)

| 빠진 항목 | 이유 |
|---|---|
| `server/api/` (upload/analysis/members) | PRD-4 범위. 분석 파이프라인 코어와 분리하기 위해 제외 |
| `server/main.py` (FastAPI 앱) | PRD-4. `analyzer.run_full_analysis_with_output` 만 호출하면 동일 결과 |
| `server/storage/` (uploads/renders/reports) | 런타임 산출물. `output_dir` 인자로 자유 지정 가능 |
| `server/venv/`, `__pycache__/` | 로컬 환경 잔재 |
| `app/` (React Native) | PRD-5/6 범위 |
| `docs/PRD-4 ~ PRD-7` | API/앱/통합 단계 명세 |
| `docs/INTEGRATION_TEST_CHECKLIST.md` | PRD-7 통합 환경용 체크리스트 |
| `server/tests/test_api.py` | PRD-4 API 라우터 테스트 |
| `server/dongwook*.mp4`, `pace6/630/7.mp4`, `debug_overlay*.mp4` | 추가 페이스 샘플·디버깅용 영상. `pace530.mp4` 하나로 모든 테스트 통과 |
| `server/analyze_spikes.py`, `debug_overlay.py` | 일회성 디버깅 스크립트 |
| `server/analysis_result.json`, `uvicorn.*.log`, `uploads_baseline.txt` | 런타임 캐시/로그 |

---

## 3. 빠르게 돌려보기

```bash
# 1) 가상환경 + 의존성
cd server
python -m venv venv
# Windows: venv\Scripts\activate    /   macOS·Linux: source venv/bin/activate
pip install -r requirements.txt

# 2) CLI 단독 실행 (storage/ 없이 핵심 분석만)
python run_analysis.py pace530.mp4
#   → 콘솔에 요약 출력, analysis_result.json 저장

# 3) 산출물까지 한 번에 (PRD-3 전체)
python -c "from analyzer import run_full_analysis_with_output; \
           print(run_full_analysis_with_output('pace530.mp4', './out'))"
#   → ./out/renders/<id>.mp4 (스켈레톤 영상)
#   → ./out/reports/<id>.csv  (프레임별 CSV)
#   → 반환 dict 안에 coach_message(한국어 문장) 포함

# 4) 테스트
pytest                # 전체
pytest -m "not slow"  # 빠른 테스트만 (벤치마크 제외)
```

---

> 📌 **프론트엔드 인수인계 시 합의 사항**: API 설계는 백엔드 작업자 자유. 단, 응답 본문은 `models/analysis_result.py`의 `AnalysisResult`를 그대로 직렬화하거나, 변경한다면 프론트엔드 작업자와 합의 후 스키마 문서 1장 작성 권장.

## 4. 공개 API (이 코드만 import 하면 됨)

```python
from analyzer import (
    run_full_analysis,               # 분석만 (AnalysisResult 반환)
    run_full_analysis_with_output,   # 분석 + 렌더 + CSV + 코칭 메시지
)
from models.analysis_result import AnalysisResult
from video_validator import validate, VideoValidationError
```

- **`run_full_analysis(video_path) -> AnalysisResult`**
  - PRD-8 검증 → 33 keypoints 추출 → 5단계 전처리 → 좌/우 착지 검출 → 3대 지표 + 비대칭 → 신뢰도 산출
  - 실패 시 `VideoValidationError` (해상도/fps/길이 미충족)

- **`run_full_analysis_with_output(video_path, output_dir) -> dict`**
  - 위 + PRD-3 산출물 생성
  - 반환: `{"analysis_result", "rendered_video_path", "csv_report_path", "coach_message"}`
  - **중요**: `raw_df` 를 한 번만 추출해서 분석/렌더가 공유 (성능 최적화, 2026-05-16)

`AnalysisResult` 스키마는 `models/analysis_result.py` 참고. 필드 추가 시 모바일 앱(별도 핸드오프)과 합의 필요.

---

## 5. 절대 손대지 말 것 (PRD-0 §1)

| 항목 | 값 | 변경 시 영향 |
|---|---|---|
| AI 모델 | MediaPipe Pose (BlazePose) heavy | HEEL/FOOT_INDEX 좌표 없는 모델 사용 시 착지 검출 불가 |
| `model_complexity` | 2 (Heavy) | 0/1 은 정확도 부족 |
| 처리 방식 | 후처리 (post-processing) | 실시간 처리 시도 시 정확도 급락 |
| UI/메시지 언어 | 한국어 100% | 영문 단독 금지 |
| 환경 | 실내 트레드밀 측면 | 야외/정면/위 각도 영상 분석 정확도 보장 X |
| 임계값 위치 | `config.py` 만 | 코드 내 매직 넘버 금지 |

---

## 6. 필독 순서 (시간 없을 때)

1. `docs/PRD-0-context.md` — 전체 컨텍스트 (5분)
2. `docs/PRD-3-render-coach.md` §"흔한 함정" — 렌더링 lag·skeleton_df vs df 차이 (5분)
3. `server/config.py` — 임계값 한 눈에 (3분)
4. `server/analyzer/__init__.py` — 파이프라인 흐름도 (3분)
5. `docs/KNOWN_ISSUES.md` — 현재 알려진 한계 (3분)

학술 근거가 필요하면 `docs/REFERENCES.md` (12종 1차 검증 완료, 2026-05-17).

---

## 7. 핸드오프 시점 & 연락처

- **핸드오프 시점**: 2026-05-18
- **PRD-1~3 완료 상태**: ✅ (PRD-4~8 도 메인 리포에는 구현되어 있으나 본 폴더 범위 밖)
- **검증 시나리오 6 통과**: 비대칭 false positive 해결 + Hybrid 임계 재조정 완료
- **문의**: 메인 리포 `docs/` 안의 PRD 문서가 일차 소스. 코드 변경 시 PRD 문서도 함께 업데이트하는 컨벤션입니다.
