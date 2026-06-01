# PRD-1: Pose 추출 & 전처리 파이프라인

> 📍 항상 함께 참조: **[PRD-0-context.md](./PRD-0-context.md)**
> 📍 관련 단계: **[PRD-8-video-input-spec.md](./PRD-8-video-input-spec.md)** (입력 검증/품질)

---

## 🎯 이 단계의 목표

영상 파일을 입력받아 **MediaPipe Pose Tasks API (heavy 모델)** 로 33개 keypoints 시계열을 추출하고, **5단계 전처리 파이프라인** 으로 측면 트레드밀 환경 특유의 노이즈(self-occlusion, 단일 프레임 spike, L/R identity 혼동) 를 정리한 깨끗한 DataFrame 을 반환하는 모듈을 구현한다.

### 전처리 파이프라인 (최종)

```
raw landmarks
  ↓ 1) mask_low_visibility       (visibility < 0.4 → NaN)
  ↓ 2) hampel_filter             (단일 프레임 spike 제거)
  ↓ 3) correct_lr_swaps          (좌/우 identity 보정)
  ↓ 4) forward_fill_with_limit   (최대 10프레임)
  ↓ 5) one_euro_filter           (적응형 평활화, EMA 대체)
analysis-ready DataFrame
```

EMA 가 아니라 **One Euro Filter** 를 쓰는 이유: 30fps 측면 영상에서 다리는 정지(상체) ↔ 빠른 스윙(발) 의 속도 격차가 크다. 고정 α 의 EMA 는 정지엔 부드럽지만 빠른 동작에 lag, 빠른 동작에 맞추면 정지에 jitter. One Euro 는 `cutoff = min_cutoff + β·|dx/dt|` 로 속도에 따라 자동 적응 (Casiez et al. 2012, MediaPipe/Apple Vision 등 상용 표준).

---

## 📥 입력 (의존성)

- **이전 단계**: 없음 (프로젝트 시작점)
- **필수 참조**: `PRD-0-context.md`
- **외부 의존**:
    - `mediapipe >= 0.10.35` (Tasks API. legacy `mp.solutions` 미사용)
    - `opencv-python`, `numpy`, `pandas`, `scipy`
    - 모델 파일 `pose_landmarker_heavy.task` (자동 다운로드)

---

## ✅ 완료 조건 (Definition of Done)

- [ ] `server/config.py` 에 모든 임계값 상수 정의 완료
- [ ] `pose_extractor.py` 가 mp4 → 33 keypoints 시계열 DataFrame 반환
- [ ] **Tasks API (`PoseLandmarker`) 사용** + heavy 모델 자동 다운로드
- [ ] `MEDIAPIPE_MODEL_COMPLEXITY = 2` 명시적 적용 확인
- [ ] `preprocessor.py` 에 5단계 파이프라인 모두 구현
    - [ ] `mask_low_visibility` (threshold 0.4)
    - [ ] `hampel_filter` (window=5, k=3)
    - [ ] `correct_lr_swaps` (보수적: gain>0.10 AND ratio<0.4)
    - [ ] `forward_fill_with_limit` (max 10 frames)
    - [ ] `one_euro_filter_array` (적응형 평활화)
- [ ] `filters.py` 에 `OneEuroFilter` 클래스 + 배열 헬퍼 구현
- [ ] `foot_strike_detector.py` 가 좌/우 발목 독립 추적 + 쿨다운 10프레임
- [ ] 디버그용 `despike_pose_dataframe` (단계 1-3만, lag 0) 제공
- [ ] `pytest tests/test_preprocessor.py` 통과 (23+ 테스트)
- [ ] 샘플 영상으로 end-to-end 동작 확인 + 디버그 오버레이 시각 검증

---

## 📋 작업 항목

### 1. `server/config.py` (모든 상수 한 곳에)

```python
# === MediaPipe 설정 ===
# PRD-0 절대 준수: complexity=2 고정.
MEDIAPIPE_MODEL_COMPLEXITY = 2
MEDIAPIPE_MIN_DETECTION_CONFIDENCE = 0.5
MEDIAPIPE_MIN_TRACKING_CONFIDENCE = 0.5

# === 전처리 ===
# PRD-1 권장 0.5 였으나 측면 트레드밀의 상수적 self-occlusion 으로 0.4 완화.
# 한쪽 다리가 다른 다리에 가려지는 구간이 영상 내내 발생하므로.
VISIBILITY_THRESHOLD = 0.4

MAX_FORWARD_FILL_FRAMES = 10        # 30fps 기준 약 0.33초

# Hampel 필터 (단일 프레임 spike 제거).
HAMPEL_WINDOW = 5                   # 홀수. 30fps 기준 ~167ms.
HAMPEL_THRESHOLD_K = 3.0            # 3-sigma 등가.

# One Euro Filter (적응형 평활화, EMA 대체).
ONE_EURO_MIN_CUTOFF = 1.5           # Hz. 작을수록 더 부드럽지만 lag.
ONE_EURO_BETA = 0.10                # 속도 적응 강도. 클수록 빠른 동작에 민감.
ONE_EURO_D_CUTOFF = 1.0             # 도함수 추정용 cutoff.

# 좌/우 identity 보정 (cyclic motion 의 false positive 방지를 위해 보수적).
LR_SWAP_MIN_GAIN = 0.10             # 거리 감소 절댓값 임계 (정규화 좌표).
LR_SWAP_RATIO = 0.4                 # swap_cost / normal_cost 가 이 값 이하여야.

# (호환성 보존; 파이프라인은 더 이상 사용하지 않음.)
EMA_ALPHA = 0.3

# === 착지 판별 ===
FOOT_STRIKE_COOLDOWN_FRAMES = 10

# === 영상 ===
TARGET_FPS = 30
TARGET_RESOLUTION = (1280, 720)

# === 색상 (BGR for OpenCV) ===
COLOR_SAFE_BGR    = (94, 197, 34)
COLOR_WARNING_BGR = (8, 179, 234)
COLOR_DANGER_BGR  = (68, 68, 239)
```

### 2. `server/analyzer/pose_extractor.py` — Tasks API

**핵심 변경**: `mediapipe.solutions.pose.Pose` 는 v0.10.35 부터 제거됨 → **`mediapipe.tasks.python.vision.PoseLandmarker`** 사용.

```python
from mediapipe.tasks.python import BaseOptions
from mediapipe.tasks.python.vision import (
    PoseLandmarker, PoseLandmarkerOptions, RunningMode,
)

# legacy 와 동일한 인덱스/네이밍을 유지 (33 keypoints 의 BlazePose 표준).
class PoseLandmark(IntEnum):
    NOSE = 0
    LEFT_EYE_INNER = 1
    ...
    RIGHT_FOOT_INDEX = 32


def _model_path() -> Path:
    """
    complexity=2 → pose_landmarker_heavy.task 자동 다운로드.
    캐시: server/.models/
    """
    ...


def extract_pose_series(video_path: str) -> pd.DataFrame:
    """
    Returns:
        DataFrame.
            컬럼: frame_idx, timestamp_sec,
                  {landmark}_x, {landmark}_y, {landmark}_z, {landmark}_visibility (33개)
            attrs: {"fps": float, "frame_count": int, "video_path": str}

    중요:
        - visibility 무관하게 raw 좌표 그대로 저장 (가시화 친화).
        - 분석용 마스킹은 preprocess_pose_dataframe 에서 일괄 수행 (책임 분리).
    """
    options = PoseLandmarkerOptions(
        base_options=BaseOptions(model_asset_path=str(_model_path())),
        running_mode=RunningMode.VIDEO,
        num_poses=1,
        min_pose_detection_confidence=MEDIAPIPE_MIN_DETECTION_CONFIDENCE,
        min_pose_presence_confidence=MEDIAPIPE_MIN_DETECTION_CONFIDENCE,
        min_tracking_confidence=MEDIAPIPE_MIN_TRACKING_CONFIDENCE,
        output_segmentation_masks=False,
    )
    with PoseLandmarker.create_from_options(options) as landmarker:
        for frame_idx, frame_bgr in iter_frames(...):
            frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=frame_rgb)
            timestamp_ms = int(round(frame_idx * 1000.0 / fps))
            result = landmarker.detect_for_video(mp_image, timestamp_ms)
            ...
```

### 3. `server/analyzer/filters.py` — One Euro Filter

```python
"""
One Euro Filter (Casiez, Roussel & Vogel 2012).

cutoff(t) = min_cutoff + beta * |dx/dt|
    - 정지/저속: 낮은 cutoff → 강한 평활화 (jitter 제거)
    - 고속 이동: 높은 cutoff → 약한 평활화 (lag 없음)
"""

def _alpha(cutoff: float, dt: float) -> float:
    tau = 1.0 / (2.0 * math.pi * cutoff)
    return 1.0 / (1.0 + tau / dt)


class OneEuroFilter:
    def __init__(self, min_cutoff=1.0, beta=0.05, d_cutoff=1.0):
        ...

    def __call__(self, x: float, dt: float) -> float:
        # 1) 도함수 추정 + 평활화
        dx = (x - self._x_prev) / dt
        a_d = _alpha(self.d_cutoff, dt)
        dx_hat = a_d * dx + (1.0 - a_d) * self._dx_prev
        # 2) 적응형 cutoff
        cutoff = self.min_cutoff + self.beta * abs(dx_hat)
        # 3) 신호 평활화
        a = _alpha(cutoff, dt)
        x_hat = a * x + (1.0 - a) * self._x_prev
        ...


def one_euro_filter_array(series, fps, min_cutoff=2.0, beta=0.10, d_cutoff=1.0):
    """
    1D 배열 전체에 OneEuroFilter 인과적 적용.
    NaN 은 보존, NaN 직후 첫 유효값은 재시드.
    """
    ...
```

### 4. `server/analyzer/preprocessor.py` — 5단계 파이프라인

```python
def mask_low_visibility(df, threshold=VISIBILITY_THRESHOLD) -> pd.DataFrame:
    """visibility < threshold 인 landmark 의 x/y/z 를 NaN 마스킹."""


def hampel_filter(series, window=HAMPEL_WINDOW, k=HAMPEL_THRESHOLD_K) -> np.ndarray:
    """
    중앙값 ± k·1.4826·MAD 를 정상 범위로 정의. 벗어난 값은 median 으로 대체.
    MAD=0 (윈도우 내 변동 없음) 인데 현재 값만 다르면 그 자체로 outlier 처리.
    """


def correct_lr_swaps(df, min_gain=LR_SWAP_MIN_GAIN, ratio=LR_SWAP_RATIO):
    """
    측면 self-occlusion 으로 mediapipe 가 좌/우 다리를 뒤바꾼 프레임을 탐지.
    normal_cost vs swap_cost (이전 프레임 대비 거리 합) 비교.

    swap 조건:
        count >= 3 관절 매칭 AND
        gain (= normal_avg - swap_avg) > min_gain AND
        swap_avg / normal_avg < ratio

    러닝 cyclic motion 의 false positive 방지를 위해 두 조건 AND 로 묶음.
    대상 관절: hip, knee, ankle, heel, foot_index (다리 묶음 일괄 swap).
    """


def forward_fill_with_limit(series, max_frames=MAX_FORWARD_FILL_FRAMES) -> np.ndarray:
    """연속 결측이 max_frames 초과 시 NaN 유지."""


def preprocess_pose_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """
    분석용 5단계 파이프라인:
        1) mask_low_visibility
        2) hampel_filter        (각 좌표 컬럼)
        3) correct_lr_swaps
        4) forward_fill_with_limit (각 좌표 컬럼)
        5) one_euro_filter_array   (각 좌표 컬럼, fps 기반)

    visibility / frame_idx / timestamp_sec 컬럼은 보존.
    원본 attrs (fps 등) 도 보존.
    """


def despike_pose_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """
    디버그 가시화 전용: 1-3단계만 적용 (lag 0).
    스켈레톤 오버레이가 실제 위치와 정합하면서 spike/swap 은 정리.
    분석 파이프라인은 이 위에 forward fill + One Euro 를 얹어 사용.
    """
```

### 5. `server/analyzer/foot_strike_detector.py`

```python
def detect_foot_strikes(ankle_y_series, cooldown=FOOT_STRIKE_COOLDOWN_FRAMES) -> np.ndarray:
    """
    `scipy.signal.find_peaks(-series, distance=cooldown)` 로 Y 극소점 = 착지 시점.
    """


def detect_left_right_strikes(df: pd.DataFrame) -> dict:
    """
    좌/우 발목을 독립적으로 처리.
    Returns:
        {"left": np.ndarray, "right": np.ndarray}
    """
```

### 6. 테스트 (`server/tests/test_preprocessor.py` + `test_pose_pipeline.py`)

필수 테스트 클래스/케이스:

```python
class TestForwardFill:
    def test_fill_within_limit()
    def test_exceeds_limit_keeps_nan()
    def test_leading_nan_unchanged()

class TestEMA:               # 호환성용. 함수 자체는 보존.
    def test_first_valid_is_seed()
    def test_smoothing_formula()
    def test_reduces_variance()

class TestHampelFilter:
    def test_passthrough_when_no_outlier()
    def test_single_frame_spike_replaced()
    def test_preserves_sharp_peak_if_not_outlier()
    def test_nan_preserved()
    def test_empty_series()

class TestMaskLowVisibility:
    def test_below_threshold_masks_coords()
    def test_above_threshold_unchanged()

class TestOneEuroFilter:
    def test_passthrough_first_sample()
    def test_smooths_constant_signal()
    def test_responsive_to_fast_motion()      # ramp 입력 추적 확인
    def test_reduces_jitter_when_static()
    def test_nan_resets_state()

class TestLRSwapCorrection:
    def test_no_swap_on_normal_motion()       # cyclic motion false positive 0
    def test_detects_clear_swap()             # 명확한 swap 1회 감지
    def test_handles_missing_lr_columns_gracefully()

class TestPipelineOrder:
    def test_pipeline_includes_hampel_before_ema()
    def test_despike_only_no_ema_lag()        # 디버그 모드는 양 끝 lag 0
```

---

## 🧪 검증 방법

### 1단계: 단위 테스트

```bash
cd server
pytest tests/test_preprocessor.py tests/test_pose_pipeline.py -v
```

### 2단계: 샘플 영상 end-to-end

```python
from analyzer.pose_extractor import extract_pose_series
from analyzer.preprocessor import preprocess_pose_dataframe
from analyzer.foot_strike_detector import detect_left_right_strikes

raw = extract_pose_series("running_video.mp4")
df = preprocess_pose_dataframe(raw)
strikes = detect_left_right_strikes(df)

print(f"frames={len(df)}, fps={df.attrs['fps']}")
print(f"left strikes={len(strikes['left'])}, right={len(strikes['right'])}")
assert abs(len(strikes['left']) - len(strikes['right'])) <= 2
```

### 3단계: 디버그 오버레이 영상 (시각 검증)

`server/debug_overlay.py` 스크립트로 raw / despiked / final 세 단계 좌표를 분리해 시각화:
- 스켈레톤: `despike_pose_dataframe` (lag 0, spike 제거)
- 메트릭 텍스트 수치: `preprocess_pose_dataframe` (분석용 최종)
- 착지 마커: `detect_left_right_strikes`

```bash
python debug_overlay.py running_video.mp4 debug_overlay.mp4
```

### 4단계: spike 통계 비교

`server/analyze_spikes.py` 로 raw → despiked → final 변환 단계별 spike 감소율 객관 측정. raw 의 p95 임계값을 고정해 단계 간 apples-to-apples 비교.

---

## 💬 추천 Vibe Coding 명령

```
1. "PRD-0 + PRD-1 을 읽고 server/config.py 를 만들어줘. 모든 임계값을 한국어 주석과 함께 정의. EMA_ALPHA 는 호환성으로 보존하되 파이프라인은 One Euro 사용."

2. "server/analyzer/pose_extractor.py 구현. mediapipe Tasks API (PoseLandmarker) + heavy.task 자동 다운로드. PoseLandmark IntEnum 직접 정의 (legacy mp.solutions 제거됨)."

3. "server/analyzer/filters.py 에 OneEuroFilter 클래스 + one_euro_filter_array 헬퍼 구현. NaN 보존 + 재시드."

4. "server/analyzer/preprocessor.py 에 5단계 파이프라인 구현 (mask → hampel → lr_swap → forward_fill → one_euro). 디버그용 despike_pose_dataframe 도 함께."

5. "server/analyzer/foot_strike_detector.py 에 scipy.signal.find_peaks 로 좌/우 독립 착지 검출."

6. "tests/test_preprocessor.py, test_pose_pipeline.py 작성. Hampel MAD=0 엣지 케이스, One Euro NaN 재시드, LR swap false positive 0 확인 케이스 필수."

7. "debug_overlay.py 와 analyze_spikes.py 스크립트 작성. raw/despiked/final 3단계 좌표 분리해서 시각/통계 검증."
```

---

## 📤 산출물

### 생성될 파일

```
server/
├── config.py
├── requirements.txt
├── .models/                          # mediapipe 모델 캐시 (자동)
├── analyzer/
│   ├── __init__.py
│   ├── pose_extractor.py             # Tasks API
│   ├── filters.py                    # One Euro Filter
│   ├── preprocessor.py               # 5단계 파이프라인
│   └── foot_strike_detector.py
├── debug_overlay.py                  # 시각 검증 도구
├── analyze_spikes.py                 # 통계 검증 도구
└── tests/
    ├── __init__.py
    ├── test_pose_pipeline.py
    └── test_preprocessor.py
```

### 다음 단계로 넘길 인터페이스

```python
df: pd.DataFrame
# columns: frame_idx, timestamp_sec, {landmark}_{x,y,z,visibility} × 33
# attrs:   {"fps": float, "frame_count": int, "video_path": str}

strikes: dict[str, np.ndarray]
# {"left": [12, 45, 78, ...], "right": [27, 60, 93, ...]}
```

---

## ⚠️ 흔한 함정

1. **MediaPipe Tasks API 와 legacy API 혼동**
   - v0.10.35+ 에서 `mp.solutions.pose.Pose` 제거
   - 반드시 `from mediapipe.tasks.python.vision import PoseLandmarker` 사용
   - `PoseLandmark` 도 enum 직접 정의 (legacy 의존 X)

2. **모델 파일 다운로드 누락**
   - `pose_landmarker_heavy.task` (~30MB) 가 없으면 첫 실행 시 자동 다운로드 필요
   - 오프라인 환경에선 사전 배포 또는 수동 캐시

3. **좌표는 정규화 (0~1)**
   - 픽셀 좌표 변환 시 width/height 곱하기 필수
   - overstride / oscillation 임계값은 정규화 좌표 기준

4. **visibility 임계값 0.4 의 이유**
   - PRD 권장 0.5 였으나, 측면 트레드밀은 한 다리가 다른 다리에 가려지는 self-occlusion 이 영상 내내 발생
   - 0.5 로 두면 가려진 다리 좌표가 영상 절반에서 NaN → 분석 불가
   - 정면/사선 영상이면 0.5–0.6 으로 다시 올려야 할 수 있음

5. **전처리 순서가 중요**
   - mask 가 먼저 (NaN 명시) → Hampel 이 NaN 을 통계에서 제외 → LR swap → forward fill → One Euro
   - One Euro 가 먼저면 spike 가 평활화 되어 Hampel 이 못 잡음
   - forward fill 이 Hampel 전이면 채워진 값이 통계 왜곡

6. **좌/우 swap 보정의 false positive**
   - 러닝 cyclic motion 에서 양 다리가 만나는 순간 nearest-neighbor 만으로는 swap 감지 false positive 가 빈발
   - **반드시 두 조건 AND**: 거리 절대 감소 (`gain > 0.10`) AND 비율 (`ratio < 0.4`)
   - 실제 영상에서 0–8 회 정도가 정상 범위. 50회 이상이면 임계값 너무 헐거움

7. **One Euro 의 `min_cutoff` / `beta` 튜닝**
   - 정지 부위(머리/몸통) 위주면 `min_cutoff=1.0, beta=0.05`
   - 발/손 위주(빠른 동작) 면 `min_cutoff=4.0, beta=0.30`
   - 우리는 trade-off 중간값 `1.5 / 0.10` 사용. 측면 다리 스윙에 적합.

8. **fps 가 30 이 아닐 수 있음**
   - `df.attrs["fps"]` 에 메타데이터 fps 보존
   - One Euro 는 dt 기반이라 fps 정확해야 동작 정확
   - foot_strike 의 frame → time 변환도 이 값 사용

9. **MediaPipe Pose 의 좌/우는 "사용자 신체 기준"**
   - 영상 화면상 왼쪽 ≠ 신체의 왼쪽일 수 있음 (촬영 방향)
   - LR swap 보정은 신체 기준 ID 의 일관성을 유지하는 것이지 화면 좌/우를 바꾸지 않음

10. **빠른 페이스(4'/km 이하) + 30fps 한계**
    - 모션 블러 + 프레임 간 점프로 mediapipe 자체가 좌표를 못 잡음
    - 우리 파이프라인 튜닝으론 해결 불가 → 입력 영상 조건 (PRD-8 참조)
