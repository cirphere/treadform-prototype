# PRD-3: 렌더링 영상 & 한국어 코칭 메시지 생성

> 📍 항상 함께 참조: **[PRD-0-context.md](./PRD-0-context.md)**
> 📍 이전 단계 산출물: **[PRD-2-metrics.md](./PRD-2-metrics.md)**
> 📍 교차 참조: **[PRD-8-video-input-spec.md](./PRD-8-video-input-spec.md)** (렌더링 영상에 신뢰도 배지 합성)

---

## 🎯 이 단계의 목표

Step 2의 `AnalysisResult`를 입력받아, **3-Layer 스켈레톤 오버레이 영상 + 한국어 AI 코칭 메시지 + CSV 리포트**를 산출하는 모듈을 구현한다. Step 4(API)가 그대로 클라이언트에 반환할 최종 산출물을 만드는 단계.

**PRD-8 연계**: AnalysisResult 의 `confidence`/`warnings` 를 렌더링 영상 좌상단에 배지로 합성한다. 앱이 별도로 신뢰도를 표시하지만, 영상만 단독 공유될 수도 있어 영상 자체에도 신뢰도 정보를 박아둔다.

---

## 📥 입력 (의존성)

- **이전 단계 산출물**:
    - `AnalysisResult` Pydantic 객체 (PRD-8 의 `confidence`/`warnings` 포함)
    - 원본 영상 파일 경로
    - 전처리된 keypoints DataFrame
- **필수 참조**: `PRD-0-context.md`, `PRD-2-metrics.md`, `PRD-8-video-input-spec.md`

---

## ✅ 완료 조건 (Definition of Done)

- [ ] 3-Layer 스켈레톤 오버레이 MP4 영상 생성 (720p, 30fps, H.264)
- [ ] 상태별 색상 동적 변경 (🟢 안전 / 🟡 경고 / 🔴 위험)
- [ ] 현재 무릎 각도 + 한국어 상태 텍스트 오버레이
- [ ] Foot Strike 시점 시각적 강조 (관절 원 확대)
- [ ] **렌더링 영상 좌상단에 신뢰도 배지** ("신뢰도: 높음/보통/낮음", 색상 동일 토큰)
- [ ] **`low confidence` 시 영상 좌하단에 "참고용" 워터마크** 추가
- [ ] Danger 타임스탬프 JSON 생성
- [ ] 한국어 코칭 메시지 자연스럽게 출력
- [ ] CSV 리포트 생성 (프레임/시간별 모든 지표)
- [ ] 렌더링 출력물이 `storage/renders/`, `storage/reports/`에 저장
- [ ] 단위 테스트 + 시각적 육안 검증

---

## 📋 작업 항목

### 1. `server/analyzer/renderer.py` 구현

**역할**: 원본 영상 + keypoints + 분석 결과 → 오버레이 영상

**3-Layer 구조**:
- Layer 1: 원본 영상 (720p 베이스)
- Layer 2: 스켈레톤 라인 (상태별 색상)
- Layer 3: 텍스트 오버레이 (각도 + 한국어 상태)

**함수 시그니처**:
```python
def render_skeleton_video(
    input_video_path: str,
    output_video_path: str,
    skeleton_df: pd.DataFrame,         # despike_pose_dataframe() 결과 (lag 0)
    analysis_result: AnalysisResult
) -> str:
    """
    원본 영상에 스켈레톤 오버레이 + 텍스트 추가한 MP4 생성.

    skeleton_df 는 반드시 `despike_pose_dataframe()` 결과여야 한다 (흔한 함정 #11).
    `preprocess_pose_dataframe()` 결과를 넘기면 빠른 움직임에서 스켈레톤이
    신체에 뒤처진다. 메트릭 수치는 analysis_result 에서 읽으므로 분석용
    df 는 renderer 에 필요 없다.

    Returns: 출력 영상 절대 경로
    """

def draw_skeleton_on_frame(
    frame: np.ndarray,
    keypoints: dict,
    color_bgr: tuple
) -> np.ndarray:
    """한 프레임에 스켈레톤 라인 그리기. MediaPipe 연결 정보 사용."""

def draw_text_overlay(
    frame: np.ndarray,
    knee_angle: float,
    status_text_ko: str,
    color_bgr: tuple
) -> np.ndarray:
    """프레임에 한국어 상태 텍스트 추가. cv2.putText는 한국어 미지원이므로 PIL 사용."""

def emphasize_foot_strike(
    frame: np.ndarray,
    ankle_position: tuple,
    color_bgr: tuple
) -> np.ndarray:
    """착지 시점 발목 위치에 큰 원 그려서 강조."""
```

**중요 구현 사항**:
- **한국어 텍스트**: OpenCV `cv2.putText`는 한글 미지원 → PIL ImageDraw 사용
  ```python
  from PIL import Image, ImageDraw, ImageFont
  # cv2 frame (BGR) → PIL (RGB) 변환 → 텍스트 그리기 → 다시 cv2로
  ```
- **폰트**: 시스템의 한글 폰트 사용 (예: `C:\Windows\Fonts\malgun.ttf`, `/Library/Fonts/AppleSDGothicNeo.ttc`, `/usr/share/fonts/truetype/nanum/NanumGothic.ttf`)
- **스켈레톤 연결**: `mediapipe.solutions.pose.POSE_CONNECTIONS` 는 v0.10.35 부터 제거됨 → 자체 정의 connection 리스트 사용. 33개 landmark 의 표준 연결은 `analyzer.pose_extractor.POSE_CONNECTIONS` 로 노출 권장 (legacy 호환 인덱스 그대로).
- **신뢰도 배지 합성** (PRD-8): `AnalysisResult.confidence` 에 따라 좌상단(가로 200px × 세로 40px) 박스를 그리고 "신뢰도: 높음" 등 텍스트 표시. `low` 면 좌하단에 옅은 빨강 워터마크 "참고용 — 재촬영 권장" 추가.

### 2. `server/analyzer/coach_message.py` 구현

**역할**: 분석 결과 → 자연스러운 한국어 코칭 메시지

**템플릿 기반 생성** (Phase 1, MVP):

```python
def generate_korean_coach_message(result: AnalysisResult) -> str:
    """
    분석 결과의 status_counts를 보고 가장 문제가 큰 지표를 골라
    자연스러운 한국어 코칭 메시지 생성.

    예시 출력:
    "오늘 러닝에서 뒤꿈치 착지가 15회 발생했습니다.
     무릎 부담을 줄이려면 보폭을 약간 줄이고
     중족 부위로 착지하는 연습을 추천드립니다."
    """

# 지표별 메시지 템플릿
KNEE_MESSAGES = {
    "stiff_knee_dominant": "무릎이 충분히 굽혀지지 않아 충격이 직접 전달되고 있습니다. {count}회 발생.",
    "over_bent_dominant": "무릎이 과도하게 굽혀집니다. {count}회 발생.",
    "good_dominant": "무릎 굴곡 각도가 안정적입니다 👍",
}

FOOT_STRIKE_MESSAGES = {
    "heel_dominant": "뒤꿈치 착지가 {count}회로 다소 많이 발생했습니다. 무릎 부담을 줄이려면 보폭을 조금 줄여보세요.",
    "midfoot_dominant": "중족 착지가 안정적으로 이루어지고 있습니다 👍",
    "forefoot_dominant": "앞꿈치 착지 비율이 높습니다. 종아리 부담에 주의하세요.",
}

OVERSTRIDE_MESSAGES = {
    "over_dominant": "보폭이 과도하게 큽니다. {count}회 오버스트라이딩 검출.",
    "good": "보폭이 적절합니다 👍",
}

VERTICAL_MESSAGES = {
    "high": "상하 움직임이 크게 발생합니다. 에너지 낭비가 발생할 수 있습니다.",
    "good": "수직 진폭이 효율적입니다 👍",
}

ASYMMETRY_MESSAGES = {
    "warning": "좌우 비대칭({ratio:.0%})이 감지됩니다. 편측 부상 주의가 필요합니다.",
}
```

**메시지 우선순위 로직**:
```python
def select_priority_issues(result: AnalysisResult) -> list:
    """
    여러 지표 중 가장 심각한 문제 2~3개를 선별.

    우선순위:
    1. 비대칭 경고 (편측 부상 위험)
    2. Heel Strike 비율 50% 초과
    3. Stiff Knee 또는 Over Bent 30% 초과
    4. Overstride 30% 초과
    5. High Vertical Oscillation
    """
```

### 3. `server/analyzer/csv_reporter.py` 구현

**CSV 컬럼 구조**:
```
frame_idx, time_sec, foot,
knee_angle, knee_status,
foot_strike_angle, foot_strike_status,
overstride_distance, overstride_status,
hip_y, is_foot_strike
```

**함수 시그니처**:
```python
def generate_csv_report(
    output_csv_path: str,
    keypoints_df: pd.DataFrame,
    analysis_result: AnalysisResult
) -> str:
    """프레임별 모든 지표를 CSV로 저장. 트레이너용 객관 자료."""
```

### 4. `server/analyzer/danger_collector.py` 구현

```python
def collect_danger_timestamps(
    result: AnalysisResult,
    fps: int = TARGET_FPS
) -> list[DangerTimestamp]:
    """
    모든 지표의 per_strike에서 🔴 판정만 추출해
    DangerTimestamp 리스트 생성. 시간순 정렬.
    """
```

### 5. 통합 함수 업데이트 (`analyzer/__init__.py`)

PRD-1+2+8 단계에서 이미 `run_full_analysis(video_path) → AnalysisResult` 가 구현됨. PRD-3 는 이를 *감싸는* 새 함수를 추가한다. **PRD-7 raw_df 캐싱 최적화 (2026-05-16) 이후** 두 진입점이 공통 private helper `_analyze_from_raw_df` 를 공유한다:

```python
def _validate_or_raise(video_path: str) -> None: ...
def _analyze_from_raw_df(raw_df, video_path) -> tuple[AnalysisResult, df]: ...

def run_full_analysis(video_path: str) -> AnalysisResult:
    _validate_or_raise(video_path)
    raw_df = extract_pose_series(video_path)        # 1회만
    result, _ = _analyze_from_raw_df(raw_df, video_path)
    return result

def run_full_analysis_with_output(
    video_path: str,
    output_dir: str,
) -> dict:
    """
    Step 1+2+3+8 모든 처리를 한 번에 실행.

    내부 호출 순서:
        1. _validate_or_raise(video_path)                       (PRD-8)
        2. extract_pose_series(video_path) → raw_df             (1회만, 캐싱)
        3. _analyze_from_raw_df → (AnalysisResult, 분석용 df)   (PRD-1+2+8)
        4. despike_pose_dataframe(raw_df) → skeleton_df         (lag 0 가시화용)
        5. renderer.render_skeleton_video(...)                  (PRD-3)
           - AnalysisResult.confidence 를 좌상단 배지로 합성
           - low confidence 면 좌하단 워터마크
        6. csv_reporter.generate_csv_report(...)                (PRD-3)
        7. coach_message.generate_korean_coach_message(...)     (PRD-3)

    Raises:
        video_validator.VideoValidationError: PRD-8 하드 요건 위반 시.

    Returns:
        {
            "analysis_result": AnalysisResult,    # confidence/warnings 포함
            "rendered_video_path": str,
            "csv_report_path": str,
            "coach_message": str
        }
    """
```

> 📌 PRD-3 산출물(렌더링/CSV/코칭)은 분석 결과를 *후속 처리* 한다. 검증 실패 (`VideoValidationError`) 는 renderer 까지 가지 않으므로 상위 호출자(PRD-4 API 레이어) 가 잡아서 HTTP 400 으로 변환한다.

> 📌 **raw_df 캐싱 (PRD-7 최적화)**: 이전엔 `run_full_analysis_with_output` 가 내부적으로 `run_full_analysis` 를 호출하여 `extract_pose_series` 가 2회 실행됐고 (60fps 11초 영상 기준 약 165초), 캐싱 후 1회만 실행되어 약 116초로 단축. BENCHMARK.md 참조.

### 6. 테스트 작성

`server/tests/test_renderer.py`
- `test_render_video_exists`: 출력 파일 생성 확인
- `test_render_video_duration`: 입력 영상과 동일 길이
- `test_render_video_resolution`: 720p 유지

`server/tests/test_coach_message.py`
- `test_message_heel_dominant`: heel 비율 60% → "뒤꿈치 착지" 문구 포함
- `test_message_all_good`: 모든 지표 양호 → 긍정 메시지
- `test_message_asymmetry_warning`: 비대칭 검출 시 메시지 포함
- `test_message_natural_korean`: 어색한 표현 없음 (수동 확인)

---

## 🧪 검증 방법

### 1단계: 단위 테스트
```bash
pytest tests/test_renderer.py tests/test_coach_message.py -v
```

### 2단계: 시각적 육안 검증 (필수!)
```python
from analyzer import run_full_analysis_with_output

result = run_full_analysis_with_output(
    video_path="samples/test_run_10s.mp4",
    output_dir="storage/test_output/"
)

print(result["coach_message"])
# 출력 영상을 직접 재생해서 확인:
# - 스켈레톤 라인이 신체 따라 정확히 그려지는지
# - 색상이 상태에 맞게 변하는지
# - 한국어 텍스트가 깨지지 않고 표시되는지
# - 착지 시점에 발목 원이 강조되는지
```

### 3단계: CSV 검증
```python
import pandas as pd
df = pd.read_csv(result["csv_report_path"])
print(df.head())
assert "knee_angle" in df.columns
assert df["foot"].isin(["left", "right"]).all()
```

---

## 💬 추천 Vibe Coding 명령

```
1. "PRD-3-render-coach.md를 보고 server/analyzer/renderer.py 구현. OpenCV로 스켈레톤 라인, PIL로 한국어 텍스트, MediaPipe POSE_CONNECTIONS 사용."

2. "한글 폰트 자동 탐색 헬퍼 함수 추가. macOS/Linux/Windows 경로 모두 시도하고 첫 번째로 발견되는 폰트 반환."

3. "server/analyzer/coach_message.py에 템플릿 기반 한국어 메시지 생성기 구현. 우선순위 로직으로 가장 심각한 문제 2~3개 선별."

4. "server/analyzer/csv_reporter.py에 프레임별 모든 지표 CSV 생성 함수."

5. "server/analyzer/danger_collector.py에 🔴 판정만 추출해 DangerTimestamp 리스트 만드는 함수."

6. "analyzer/__init__.py의 run_full_analysis_with_output 함수 업데이트. Step 1+2+3 통합."

7. "tests/test_renderer.py와 tests/test_coach_message.py 작성. 어색한 한국어 표현 없는지 sample 출력도 함께 검증."

8. "samples/test_run_10s.mp4로 end-to-end 실행해서 결과 영상이 storage/renders/에 정상 생성되는지 확인."
```

---

## 📤 산출물

### 생성될 파일
```
server/
├── analyzer/
│   ├── __init__.py                  # (업데이트)
│   ├── renderer.py
│   ├── coach_message.py
│   ├── csv_reporter.py
│   └── danger_collector.py
├── storage/
│   ├── renders/{analysis_id}.mp4
│   └── reports/{analysis_id}.csv
└── tests/
    ├── test_renderer.py
    └── test_coach_message.py
```

### 다음 단계로 넘길 인터페이스

**Step 4(API)가 사용할 통합 함수**:

```python
result = run_full_analysis_with_output(
    video_path="path/to/uploaded.mp4",
    output_dir="storage/"
)

# Step 4에서 이 결과를 HTTP Response로 변환
{
    "analysis_id": "uuid",
    "rendered_video_url": f"/storage/renders/{uuid}.mp4",
    "csv_url": f"/storage/reports/{uuid}.csv",
    "coach_message_ko": result["coach_message"],
    "metrics": result["analysis_result"].model_dump(),
    ...
}
```

---

## ⚠️ 흔한 함정

1. **OpenCV는 한글 미지원**
   - 반드시 PIL ImageDraw로 한글 텍스트 그리기
   - `cv2.putText`에 한글 넘기면 `???` 출력됨

2. **폰트 경로는 시스템마다 다름**
   - macOS: `/System/Library/Fonts/AppleSDGothicNeo.ttc`
   - Ubuntu: `apt install fonts-nanum` 후 `/usr/share/fonts/truetype/nanum/NanumGothic.ttf`
   - Windows: `C:/Windows/Fonts/malgun.ttf`
   - 자동 탐색 헬퍼 작성 권장

3. **BGR vs RGB 색상**
   - OpenCV는 BGR, PIL은 RGB
   - 변환 시 `cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)`

4. **렌더링 속도가 매우 느림**
   - `model_complexity=2`로 한 번 분석 후 keypoints DataFrame을 재사용
   - 렌더링 시 MediaPipe 재호출 금지 (중복 추론)

5. **출력 파일이 크면 모바일 재생 불가**
   - `cv2.VideoWriter`의 `fourcc='mp4v'` 사용
   - 비트레이트 컨트롤이 어려우면 ffmpeg-python으로 후처리 압축 고려

6. **한국어 코칭 메시지의 자연스러움**
   - 템플릿은 반드시 사람이 읽어보고 어색함 확인
   - "~다" 종결, 부드러운 톤 유지
   - "👍" 이모지로 긍정적 피드백 차별화

7. **mediapipe legacy API 부재** _(2026-05-15, PRD-1)_
   - `mp.solutions.pose.POSE_CONNECTIONS` 는 v0.10.35 부터 제거됨
   - Tasks API 에는 동등한 상수 노출이 없으므로 `analyzer/pose_extractor.py` 에 자체 정의된 연결 리스트를 export 하고 renderer 가 그것을 import
   - 인덱스는 legacy 와 동일하게 유지하여 기존 디버그 코드 호환성 보존

8. **`run_full_analysis_with_output` vs `run_full_analysis`** _(2026-05-15)_
   - PRD-1+2+8 단계에서 `run_full_analysis(video_path) → AnalysisResult` 가 이미 구현됨
   - PRD-3 의 `_with_output` 함수는 이를 *감싸는* 새 함수일 뿐 — 기존 함수는 그대로 둘 것 (단위 테스트가 의존)
   - 잘못 리팩토링하면 PRD-4 API 의 검증 경로가 무너짐

9. **신뢰도 배지를 매 프레임 새로 그리는 낭비** _(PRD-8)_
   - confidence/warnings 는 영상 전체에 고정값 → 첫 프레임에서 만든 PIL 이미지를 캐시해 매 프레임 합성만
   - PIL 텍스트 렌더링은 비싸므로 캐시 안 하면 30fps × 30초 = 900회 재계산

10. **mediapipe `.task` 모델 캐시 위치**
    - heavy 모델은 `server/.models/pose_landmarker_heavy.task` (~30MB) 에 자동 다운로드
    - 첫 실행 시 네트워크 필요. CI/오프라인 환경에서는 사전 다운로드 스크립트 또는 commit 된 모델 파일 권장 (gitignore 주의)

11. **스켈레톤 좌표와 메트릭 좌표를 분리할 것** _(2026-05-15)_
    - `preprocess_pose_dataframe()` 의 결과(`df`)는 **forward fill + One Euro filter** 까지 적용된 분석 정확도용 좌표다. 빠른 다리 스윙 시 One Euro 의 평활 특성상 실제 신체보다 시각적으로 뒤처지고, forward fill 구간에서는 직전 좌표가 stale 하게 남아 스켈레톤이 "멈췄다 점프" 하는 인상을 준다.
    - 가시화에는 반드시 `despike_pose_dataframe()` 결과(`skeleton_df` = Hampel + L/R swap 만 적용, lag 0) 를 사용한다. `debug_overlay.py` 가 이미 동일한 패턴을 사용 중.
    - `render_skeleton_video()` 시그니처의 첫 DataFrame 인자명은 `skeleton_df` 이며, 메트릭 수치는 모두 `analysis_result.metrics` 에서 읽으므로 renderer 는 분석용 df 를 받지 않는다.
    - CSV (`csv_reporter`) 는 hip_y 같은 보고용 수치를 평활된 좌표로 채우는 게 자연스러우므로 분석용 `df` 를 그대로 사용한다 (renderer 와 다름).
