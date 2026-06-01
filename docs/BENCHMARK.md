# TreadForm 성능 벤치마크

## 측정 방법

```powershell
Set-Location server
venv\Scripts\python -m pytest tests\test_benchmark.py -v -s -m benchmark
```

기본 `pytest` 실행에선 `pytest.ini` 의 `addopts = -m "not benchmark"` 로 자동 제외된다.

## 테스트 환경

| 항목 | 사양 |
|---|---|
| OS | Windows 11 Home |
| Python | 3.13.12 (server/venv) |
| MediaPipe | ≥ 0.10.35 (Tasks API, Heavy 모델) |
| model_complexity | 2 |
| 입력 영상 | **60fps 1920×1080** (pace530/7/630.mp4) |
| 측정 일자 | 2026-05-16 |
| 측정 도중 호스트 상태 | Android 에뮬레이터 + Metro + uvicorn 동시 가동 (background 부하 있음) |

## 측정 결과 (영상 길이별)

`tests/test_benchmark.py` 출력 그대로 (각 1회 측정):

| 영상 | duration | strikes | danger | confidence | elapsed | ratio (영상:분석) |
|---|---|---|---|---|---|---|
| pace530.mp4 | 8.5초 | 32 | 0 | high | **95.04초** | 1 : 11.16 |
| pace7.mp4   | 11.1초 | 35 | 0 | high | **115.87초** | 1 : 10.42 |
| pace630.mp4 | 16.2초 | 53 | 0 | high | **173.92초** | 1 : 10.72 |

→ 60fps 1080p 입력 기준 **분석/영상 ≈ 10.7배** 의 일관된 비율.

## 동시 처리

동일 영상(pace7.mp4, 11.1초) 3개를 `ThreadPoolExecutor(max_workers=3)` 로 병렬 실행:

| 항목 | 값 |
|---|---|
| total wall-clock | 184.47초 |
| individual elapsed | [181.97, 184.45, 183.38] 초 |
| individual 평균 | 183.27초 |
| 단일 처리 × 3 시 (이론 직렬) | 347.61초 |
| **병렬화로 단축된 비율** | **53%** (1.88배 효율, 이상적 3배 대비 63%) |

→ MediaPipe Pose 자체가 멀티스레드를 사용하므로 동시 3 요청은 CPU 코어를 나눠 쓰며 각 요청이 ~1.6배 느려진다. **2 요청까지는 안정적, 3 이상은 큐잉 권장** (W-001 참고).

## raw_df 캐싱 최적화 효과 (2026-05-16, PRD-7)

`run_full_analysis_with_output` 가 `extract_pose_series` 를 1회만 호출하도록 리팩토링.

- **이전**: `run_full_analysis` 안 (1회) + `_with_output` 안 (1회) = 총 2회 → 60fps 11초 영상이 약 165초.
- **현재**: `_validate_or_raise` + `extract_pose_series` 1회 → `_analyze_from_raw_df` 가 (AnalysisResult, df) 반환 → `despike_pose_dataframe(raw_df)` 만 추가 호출.
- **측정**: 11.1초 영상 115.87초. **약 30% 단축** (165초 → 116초).
- **이유**: 분석 파이프라인 비용의 ~50% 가 pose 추출. 두 번 호출 → 한 번으로 줄어든 만큼 그대로 절감.

## 자원 사용량

`psutil` 미설치 환경에서 측정 — `mem_delta_mb` 항목은 stdout 에 출력되지 않았다. 향후 `psutil` 추가 후 재측정 예정. 측정 중 호스트의 가용 RAM 은 약 4~5GB 였고 (16GB 중 11GB+ 이미 점유), 모든 측정이 swap 없이 완료됨.

## 결론

- **60초 이내 분석 목표는 PRD-7 가정 환경(M2 Pro 10-core 등 강력한 CPU)에서 유효**. 현재 측정 환경(Windows 11 + 동시 부하)에서는 60fps 1080p 입력 기준 ~10.7배 비율, 즉 6초 영상이 약 60초로 가까스로 들어옴.
- **raw_df 캐싱은 즉시 효과**가 있었다 (-30%). 단일 최적화로 가장 큰 단축.
- **Pose 추출이 전체의 ~50% 차지** (기존 메모리 추정치 79% 보다 낮음 — 1080p 입력 + 단계별 측정 부재로 정확도 한계).
- 동시 처리는 2 요청까지 권장. **단계별 instrumentation 도입 + 720p 입력 표준화 시 추가 단축 여지가 가장 크다.**

## 향후 최적화 방향

1. **720p 표준 입력**: 1080p → 720p 다운스케일 후 분석 입력 (앱이 이미 720p 변환을 PRD-5 에 포함하지만 현재 우회). 픽셀 4.5분의 1 → mediapipe 추론 ~2~3배 빨라질 전망.
2. **단계별 instrumentation**: `_analyze_from_raw_df` 안에 `time.perf_counter()` 라벨을 삽입해 추출/전처리/지표/렌더링 비율 확정.
3. **MediaPipe GPU/MPS/CUDA 가속**: Windows 에서 OpenGL/Vulkan delegate 또는 Linux/macOS GPU.
4. **psutil 추가 후 메모리 프로파일 재측정**.
5. **30fps → 15fps 다운샘플링 옵션** (정확도 trade-off 평가 필요).
6. **3 동시 이상 시 큐잉**: FastAPI BackgroundTasks 위에 Celery/Redis Queue.
