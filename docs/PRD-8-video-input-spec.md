# PRD-8: 입력 영상 사양 & 검증

> 📍 항상 함께 참조: **[PRD-0-context.md](./PRD-0-context.md)**
> 📍 관련 단계: **[PRD-1-pose-pipeline.md](./PRD-1-pose-pipeline.md)** (서버 검증), **[PRD-5-app-capture.md](./PRD-5-app-capture.md)** (앱 가이드)

---

## 🎯 이 단계의 목표

분석에 적합한 입력 영상의 **기술적/촬영적 조건**을 정의하고, 서버에서 자동 검증 + 신뢰도 평가 + 사용자 안내까지 일관되게 처리하도록 한다.

**배경**: MediaPipe heavy + Hampel + One Euro 파이프라인이 자체 정확도 천장에 도달했으나, 입력 영상이 빠른 페이스(4'/km 이하)일 때 30fps + 셔터 1/60s 의 **모션 블러 + 프레임 간 점프** 로 인해 스켈레톤이 실제 신체를 따라가지 못하는 현상 확인. 알고리즘이 아니라 입력 정보량의 한계이므로 영상 사양 자체에 가드레일이 필요.

> ✅ **구현 완료 (2026-05-15)**: `config.py` 상수 12개 + `video_validator.py` + `analyzer/quality_assessor.py` + `AnalysisResult.confidence/warnings` + `run_full_analysis` 통합 + 단위 테스트 31개 전부 통과. 실제 영상 검증 시 발견된 **세로 영상 케이스** 는 `PORTRAIT_NOT_SUPPORTED` 코드로 별도 거부하도록 보강함.

---

## 📥 입력 (의존성)

- **이전 단계**: PRD-1 (pose 파이프라인 완성)
- **필수 참조**: `PRD-0-context.md`, `PRD-1-pose-pipeline.md`
- **외부 의존**: `ffmpeg-python` 또는 `av` (메타데이터 추출), 기존 MediaPipe 결과

---

## ✅ 완료 조건 (Definition of Done)

- [x] `server/video_validator.py` 모듈 생성: 메타데이터 기반 하드 요건 검사 (portrait 거부 포함)
- [x] `server/analyzer/quality_assessor.py` 모듈 생성: pose 결과 기반 소프트 경고 산출
- [x] `AnalysisResult` 에 `confidence: "high" | "medium" | "low"` + `warnings: list[QualityWarning]` 필드 추가
- [x] `config.py` 에 모든 임계값 상수 추가 (매직 넘버 금지)
- [x] 분석 파이프라인 시작 전 하드 요건 검증 → 실패 시 `VideoValidationError` 발생 + 구체적 사유 반환
- [x] 분석 완료 후 소프트 경고 산출 → 결과에 동봉
- [x] 단위 테스트 통과 (`tests/test_video_validator.py` 15개 + `tests/test_quality_assessor.py` 16개)
- [ ] 앱(PRD-5) 의 촬영 가이드 텍스트가 본 문서의 권장사항과 일치 (앱 구현 단계에서)

---

## 📋 작업 항목

### 1. `server/config.py` 에 추가할 상수 _(실제 추가됨, `# 11. 입력 영상 사양 (PRD-8)` 섹션)_

```python
# === 하드 요건 (미충족 시 분석 거부) ===
MIN_VIDEO_WIDTH = 1280
MIN_VIDEO_HEIGHT = 720
MIN_VIDEO_FPS = 30
MIN_VIDEO_DURATION_SEC = 5
MAX_VIDEO_DURATION_SEC = 60
# 분석 가능 프레임 비율 하한 (사후 검증이므로 소프트 경고로 분류).
MIN_DETECTED_FRAME_RATIO = 0.70

# === 소프트 경고 임계값 ===
WARN_HIGH_CADENCE_SPM = 190         # ≥ 이 값 AND fps < 60 → 경고
WARN_FPS_FOR_HIGH_CADENCE = 60
WARN_LOW_AVG_VISIBILITY = 0.60
WARN_SIDE_ANGLE_DEVIATION = 0.25    # 양 어깨 x거리 / 토르소 길이
WARN_CAMERA_SHAKE_PIXELS = 3.0      # (현재 미사용, 추후 확장)

# === 신뢰도 등급 (경고 개수 기반) ===
CONFIDENCE_HIGH_MAX_WARNINGS = 0       # 0개 → high
CONFIDENCE_MEDIUM_MAX_WARNINGS = 2     # 1~2개 → medium, 3개+ → low
```

> 📌 방향 검사(`PORTRAIT_NOT_SUPPORTED`)는 별도 상수 없이 `meta.height > meta.width` 로 직접 판정한다 — 검사 자체가 매개변수가 없는 불변 규칙이기 때문.

### 2. `server/video_validator.py` (하드 요건 검사)

실제 구현된 검사 순서:

```
1. probe()             → ValueError → CANNOT_OPEN_VIDEO
2. height > width      → PORTRAIT_NOT_SUPPORTED   (방향이 해상도 검사보다 먼저)
3. width<MIN or height<MIN → RESOLUTION_TOO_LOW
4. fps < MIN_VIDEO_FPS → FPS_TOO_LOW
5. duration < MIN      → DURATION_TOO_SHORT
6. duration > MAX      → DURATION_TOO_LONG
```

```python
"""
업로드된 영상의 메타데이터를 검사해 분석 가능 여부를 판정 (PRD-8 하드 요건).
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import cv2

from config import (
    MAX_VIDEO_DURATION_SEC,
    MIN_VIDEO_DURATION_SEC,
    MIN_VIDEO_FPS,
    MIN_VIDEO_HEIGHT,
    MIN_VIDEO_WIDTH,
)


@dataclass
class VideoMeta:
    width: int
    height: int
    fps: float
    duration_sec: float
    frame_count: int


@dataclass
class ValidationResult:
    ok: bool
    meta: VideoMeta | None
    reason_code: str | None        # 로깅/API 응답용
    reason_message_ko: str | None  # 사용자 표시용


class VideoValidationError(Exception):
    """analyzer 파이프라인에서 검증 실패를 시그널링하는 예외."""

    def __init__(self, code: str, message_ko: str) -> None:
        super().__init__(f"{code}: {message_ko}")
        self.code = code
        self.message_ko = message_ko


def validate(video_path: str | Path) -> ValidationResult:
    try:
        meta = probe(video_path)
    except Exception:
        return ValidationResult(False, None, "CANNOT_OPEN_VIDEO",
            "영상 파일을 열 수 없습니다. 다시 업로드해주세요.")

    # 세로 영상 거부 (해상도 검사보다 먼저).
    if meta.height > meta.width:
        return ValidationResult(False, meta, "PORTRAIT_NOT_SUPPORTED",
            f"세로 영상은 분석할 수 없습니다 ({meta.width}×{meta.height}). "
            "휴대폰을 가로로 돌려 다시 촬영해주세요.")

    if meta.width < MIN_VIDEO_WIDTH or meta.height < MIN_VIDEO_HEIGHT:
        return ValidationResult(False, meta, "RESOLUTION_TOO_LOW",
            f"해상도가 너무 낮습니다 ({meta.width}×{meta.height}). "
            f"최소 {MIN_VIDEO_WIDTH}×{MIN_VIDEO_HEIGHT} 이상 필요합니다.")
    # ... fps / duration 검사 (생략)
    return ValidationResult(True, meta, None, None)
```

### 3. `server/analyzer/quality_assessor.py` (소프트 경고 산출)

```python
"""
Pose 추출 결과를 사용해 영상 품질 경고를 산출.

video_validator 가 하드 요건을 통과시킨 영상에 대해서만 호출된다.
분석을 막지는 않고, 결과에 confidence + warnings 로 첨부된다.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from config import (
    CONFIDENCE_HIGH_MAX_WARNINGS,
    CONFIDENCE_MEDIUM_MAX_WARNINGS,
    MIN_DETECTED_FRAME_RATIO,
    WARN_CAMERA_SHAKE_PIXELS,
    WARN_FPS_FOR_HIGH_CADENCE,
    WARN_HIGH_CADENCE_SPM,
    WARN_LOW_AVG_VISIBILITY,
    WARN_SIDE_ANGLE_DEVIATION,
)


@dataclass
class QualityReport:
    confidence: str               # "high" | "medium" | "low"
    warnings: list[dict] = field(default_factory=list)  # {code, message_ko}
    metrics: dict = field(default_factory=dict)         # 디버그용


def _detected_frame_ratio(df: pd.DataFrame) -> float:
    """left_hip_x 가 NaN 이 아닌 프레임 비율 (raw 기준)."""
    if "left_hip_x" not in df.columns or len(df) == 0:
        return 0.0
    return float(df["left_hip_x"].notna().mean())


def _avg_visibility(df: pd.DataFrame) -> float:
    cols = [c for c in df.columns if c.endswith("_visibility")]
    if not cols:
        return 0.0
    return float(df[cols].mean().mean())


def _estimate_cadence_spm(strikes_left: np.ndarray, strikes_right: np.ndarray, fps: float, n_frames: int) -> float:
    total = len(strikes_left) + len(strikes_right)
    duration_min = (n_frames / fps) / 60.0 if fps > 0 else 0.0
    return total / duration_min if duration_min > 0 else 0.0


def _side_angle_deviation(df: pd.DataFrame) -> float:
    """양 어깨 x 좌표 차이의 절댓값 / 어깨~힙 거리 (정면=큼, 측면=작음)."""
    if "left_shoulder_x" not in df.columns or "right_shoulder_x" not in df.columns:
        return 0.0
    dx = (df["left_shoulder_x"] - df["right_shoulder_x"]).abs()
    # 정규화: 어깨~힙 세로 거리.
    if "left_hip_y" in df.columns and "left_shoulder_y" in df.columns:
        torso = (df["left_hip_y"] - df["left_shoulder_y"]).abs()
        ratio = (dx / torso).replace([np.inf, -np.inf], np.nan).dropna()
        return float(ratio.median()) if len(ratio) else 0.0
    return float(dx.median())


def assess(
    raw_df: pd.DataFrame,
    fps: float,
    cadence_spm: float,
) -> QualityReport:
    warnings: list[dict] = []
    metrics: dict = {}

    # 1. 검출률.
    ratio = _detected_frame_ratio(raw_df)
    metrics["detected_frame_ratio"] = ratio
    if ratio < MIN_DETECTED_FRAME_RATIO:
        warnings.append({
            "code": "LOW_DETECTION_RATIO",
            "message_ko": f"사람이 검출되지 않은 프레임이 많습니다 ({ratio*100:.0f}%). "
                          f"전신이 화면에 들어오도록 촬영해주세요.",
        })

    # 2. 평균 visibility.
    avg_vis = _avg_visibility(raw_df)
    metrics["avg_visibility"] = avg_vis
    if avg_vis < WARN_LOW_AVG_VISIBILITY:
        warnings.append({
            "code": "LOW_VISIBILITY",
            "message_ko": "관절 인식 신뢰도가 낮습니다. "
                          "조명이 밝은 곳에서 몸에 붙는 옷으로 촬영하면 정확도가 향상됩니다.",
        })

    # 3. 빠른 페이스 + 저fps.
    metrics["cadence_spm"] = cadence_spm
    if cadence_spm >= WARN_HIGH_CADENCE_SPM and fps < WARN_FPS_FOR_HIGH_CADENCE:
        warnings.append({
            "code": "HIGH_CADENCE_LOW_FPS",
            "message_ko": f"페이스가 빠릅니다 (cadence {cadence_spm:.0f} spm). "
                          f"60fps 이상으로 촬영하면 정확도가 향상됩니다.",
        })

    # 4. 측면 각도 이탈.
    side_dev = _side_angle_deviation(raw_df)
    metrics["side_angle_deviation"] = side_dev
    if side_dev > WARN_SIDE_ANGLE_DEVIATION:
        warnings.append({
            "code": "NOT_SIDE_VIEW",
            "message_ko": "측면 촬영이 아닌 것으로 보입니다. "
                          "트레드밀 옆에서 골반 높이로 촬영해주세요.",
        })

    # 5. 신뢰도 등급.
    n = len(warnings)
    if n <= CONFIDENCE_HIGH_MAX_WARNINGS:
        confidence = "high"
    elif n <= CONFIDENCE_MEDIUM_MAX_WARNINGS:
        confidence = "medium"
    else:
        confidence = "low"

    return QualityReport(confidence=confidence, warnings=warnings, metrics=metrics)
```

### 4. `models/analysis_result.py` 확장

```python
class QualityWarning(BaseModel):
    code: str
    message_ko: str


class AnalysisResult(BaseModel):
    # ... 기존 필드 ...
    confidence: Literal["high", "medium", "low"]
    warnings: list[QualityWarning] = []
```

### 5. `analyzer/__init__.py` 의 `run_full_analysis` 통합

```python
def run_full_analysis(video_path: str) -> AnalysisResult:
    # 1. 하드 요건 검증.
    validation = video_validator.validate(video_path)
    if not validation.ok:
        raise VideoValidationError(validation.reason_code, validation.reason_message_ko)

    # 2. Pose 추출 + 전처리.
    raw_df = extract_pose_series(video_path)
    df = preprocess_pose_dataframe(raw_df)
    fps = float(df.attrs.get("fps", TARGET_FPS))

    # 3. 메트릭 계산.
    strikes = detect_left_right_strikes(df)
    metrics_result = compute_all_metrics(df, strikes)

    # 4. 품질 평가.
    cadence_spm = (len(strikes["left"]) + len(strikes["right"])) / (len(df) / fps / 60.0)
    quality = quality_assessor.assess(raw_df, fps, cadence_spm)

    return AnalysisResult(
        ...,
        confidence=quality.confidence,
        warnings=[QualityWarning(**w) for w in quality.warnings],
    )
```

### 6. API 레이어 (PRD-4) 변경

`POST /api/upload` 검증 실패 응답 — `VideoValidationError` 를 HTTP 400 으로 매핑:

```json
HTTP 400
{
  "error_code": "PORTRAIT_NOT_SUPPORTED",
  "message_ko": "세로 영상은 분석할 수 없습니다 (1080×1920). 휴대폰을 가로로 돌려 다시 촬영해주세요."
}
```

가능한 `error_code` 전체:
`CANNOT_OPEN_VIDEO`, `PORTRAIT_NOT_SUPPORTED`, `RESOLUTION_TOO_LOW`, `FPS_TOO_LOW`, `DURATION_TOO_SHORT`, `DURATION_TOO_LONG`

분석 완료 응답에 신뢰도/경고 추가:

```json
{
  "analysis_id": "...",
  "status": "completed",
  "confidence": "medium",
  "warnings": [
    {"code": "HIGH_CADENCE_LOW_FPS", "message_ko": "..."}
  ],
  "metrics": { ... }
}
```

### 7. 앱(PRD-5) 의 사용자 가이드 텍스트

촬영 화면 진입 시 모달로 표시 (`src/i18n/ko.json` 확장):

```json
{
  "captureGuide": {
    "title": "정확한 분석을 위한 촬영 가이드",
    "checklist": [
      "카메라를 삼각대/거치대로 고정",
      "트레드밀 옆에서 골반 높이로 촬영",
      "전신이 화면의 60-80% 차지",
      "단색 배경, 밝은 조명",
      "몸에 붙는 옷 (헐렁한 옷 X)",
      "5-30초 분량 (10보 이상)",
      "편안하게 5분 이상 유지 가능한 페이스로 (5:30–6:30/km 권장)"
    ],
    "settings": {
      "title": "권장 촬영 설정",
      "items": [
        "해상도: 1080p 이상",
        "프레임률: 60fps (빠른 러너 필수, 일반 30fps)",
        "셔터: 자동 (가능하면 1/250s 이상)",
        "페이스 4:30/km 이하로 분석하려면 60fps 필수"
      ]
    }
  }
}
```

결과 화면에 신뢰도 배지:

```typescript
const badgeColor = {
  high:   '#22C55E',  // SAFE
  medium: '#EAB308',  // WARNING
  low:    '#EF4444',  // DANGER
}[result.confidence];

<View style={{ backgroundColor: badgeColor }}>
  <Text>분석 신뢰도: {labelMap[result.confidence]}</Text>
</View>
{result.warnings.map(w => <Text key={w.code}>· {w.message_ko}</Text>)}
```

---

## 📐 영상 사양 요약표

### 하드 요건 (미충족 시 거부)
| 항목 | 기준 | 거부 코드 |
|---|---|---|
| 파일 열기 | cv2 로 디코드 가능 | `CANNOT_OPEN_VIDEO` |
| 방향 | 가로(landscape, `width ≥ height`) | `PORTRAIT_NOT_SUPPORTED` |
| 해상도 | ≥ 1280 × 720 | `RESOLUTION_TOO_LOW` |
| 프레임률 | ≥ 30 fps | `FPS_TOO_LOW` |
| 길이 | 5 – 60초 | `DURATION_TOO_SHORT` / `DURATION_TOO_LONG` |

> 📌 **방향 정책 (2026-05-15 추가)**: 트레드밀 측면 분석은 횡방향 움직임이 본질이므로 가로(16:9) 영상만 허용한다. 세로(9:16) 영상은 전신 + 트레드밀을 담으려면 카메라를 멀리 둬야 해 픽셀 낭비 + 모션 블러 악화. AR 가이드라인을 단일 디자인으로 유지하기 위한 PRD-0 의 "표준화된 구도" 차별화 전략과도 부합. **방향 검사는 해상도 검사보다 먼저 수행** — portrait 1080×1920 이 "해상도 너무 낮음" 으로 잘못 안내되는 것을 방지.

> 📌 **사람 검출 비율 (≥ 70%)**: 이 값은 메타데이터로 알 수 없고 pose 추출 후에야 측정 가능하므로 하드 거부가 아닌 **소프트 경고 (`LOW_DETECTION_RATIO`)** 로 분류된다.

### 소프트 경고 (분석은 진행, 신뢰도 하향)
| 항목 | 트리거 조건 |
|---|---|
| LOW_VISIBILITY | 평균 visibility < 0.60 |
| HIGH_CADENCE_LOW_FPS | cadence ≥ 190 spm AND fps < 60 |
| NOT_SIDE_VIEW | 어깨 x 차이 / 토르소 길이 > 0.25 |
| LOW_DETECTION_RATIO | 사람 검출률 < 70% (경고 모드) |

### 신뢰도 등급
| 등급 | 조건 |
|---|---|
| high | 경고 0개 |
| medium | 경고 1–2개 |
| low | 경고 3개 이상 |

### 권장 촬영 환경
- 카메라 위치: 트레드밀 측면, 러너의 골반 높이
- 해상도/fps: 1080p × 60fps (스마트폰 표준 설정)
- 셔터: 1/250s 이상 (모션 블러 최소화)
- 배경: 단색, 다른 사람 없음
- 조명: 충분히 밝게, 역광 X
- 의상: 몸에 붙는 운동복 (헐렁한 바지/긴 셔츠 회피)
- 분량: 10보 이상 (5–15초 권장)

### 권장 페이스 (촬영 속도 가이드)

분석 정확도는 **러닝 속도 × 카메라 fps** 의 함수다. PRD-8 의 `HIGH_CADENCE_LOW_FPS` 경고는 negative guardrail (이러면 신뢰도 ↓) 이고, 아래 표는 **positive guidance** (이렇게 찍어야 신뢰도 ↑) 다.

| 페이스 (분/km) | 예상 cadence | 30fps | 60fps |
|---|---|---|---|
| 7:00 이상 (조깅) | 150–160 spm | ✅ 추적 OK, 러닝 자세 미흡 | ✅ |
| **6:30 – 5:30 (sweet spot)** | **165–180 spm** | **✅ 권장 (B2C 기본)** | ✅ |
| 5:30 – 4:30 | 175–185 spm | ⚠️ 모션 블러 시작, medium 등급 위험 | ✅ 권장 |
| 4:30 – 4:00 | 185–195 spm | ❌ `HIGH_CADENCE_LOW_FPS` 경고 발생 | ✅ |
| 4:00 이하 (인터벌/sprint) | 195+ spm | ❌ 분석 신뢰도 매우 낮음 | ⚠️ 60fps 필수 |

**핵심 원칙**:
- **30fps × 200 spm = 1보당 9프레임** → 착지 시점 ±2~3 프레임 흔들림 + 모션 블러 누적.
- 일반 사용자(B2C) 가 fps 변경 옵션을 모를 가능성 큼 → **5:30–6:30/km 의 편한 페이스** 를 1차 권장.
- 트레이너 모드(B2B) 에서 본인 훈련 페이스를 분석하려면 **60fps 촬영을 필수**로 안내.
- 인터벌/sprint 분석은 **60fps + 1/500s 이상 셔터** 권장 (앱 가이드 모달에서 별도 강조).

> 📌 이 매트릭스는 `WARN_HIGH_CADENCE_SPM(190) + WARN_FPS_FOR_HIGH_CADENCE(60)` 임계값과 정합한다. 위 표의 30fps "권장" 행이 cadence 190 미만에 들어오도록 임계값이 설정되어 있다.

---

## 🧪 검증 방법

### 단위 테스트

```python
# tests/test_video_validator.py
def test_rejects_low_resolution()
def test_rejects_low_fps()
def test_rejects_too_short()
def test_rejects_too_long()
def test_passes_valid_video()
def test_handles_corrupt_file()

# tests/test_quality_assessor.py
def test_high_confidence_no_warnings()
def test_low_visibility_warning()
def test_high_cadence_low_fps_warning()
def test_side_view_deviation()
def test_confidence_grading()
```

### 통합 테스트 (실제 영상)

| 영상 | 실측 결과 (2026-05-15) |
|---|---|
| `running_video.mp4` (1280×720, 30fps, ~158 spm) | ✅ **high**, 경고 0, cadence 157.6 spm |
| `running_video_se.mp4` (1080×**1920** 세로) | 🚫 **REJECT** `PORTRAIT_NOT_SUPPORTED` |
| 가상 640×480 가로 | 🚫 REJECT `RESOLUTION_TOO_LOW` |
| 가상 1280×720 24fps | 🚫 REJECT `FPS_TOO_LOW` |
| 가상 1280×720 30fps × 3초 | 🚫 REJECT `DURATION_TOO_SHORT` |
| 가상 1280×720 30fps × 120초 | 🚫 REJECT `DURATION_TOO_LONG` |
| 가로 30fps × 4'/km 페이스 영상 | 📋 미수집 (예상: medium + `HIGH_CADENCE_LOW_FPS`) |
| 정면 촬영 영상 | 📋 미수집 (예상: medium + `NOT_SIDE_VIEW`) |

> 가로 4'/km 영상과 정면 촬영 영상은 향후 추가 수집 후 실측 필요.

---

## 💬 추천 Vibe Coding 명령

```
1. "config.py 에 PRD-8 의 입력 영상 사양 상수 추가. 하드 요건 + 소프트 경고 임계값."

2. "server/video_validator.py 구현. cv2 로 메타데이터 추출 + 4가지 하드 요건 검사 + 한국어 사유 메시지."

3. "server/analyzer/quality_assessor.py 구현. raw pose DataFrame + cadence 입력 → 4가지 경고 + 신뢰도 등급 산출."

4. "analyzer/__init__.py 의 run_full_analysis 에 검증/품질 평가 통합. AnalysisResult 에 confidence + warnings 필드 추가."

5. "tests/test_video_validator.py 와 tests/test_quality_assessor.py 작성. 각 경고 코드별 트리거 케이스 + 경계값."

6. "PRD-4 api 응답 스키마에 confidence/warnings 추가. 검증 실패 시 HTTP 400 + error_code."

7. "PRD-5 app 의 i18n/ko.json 에 captureGuide 추가. CameraScreen 진입 시 모달로 가이드 표시."

8. "PRD-6 app 의 ResultScreen 에 신뢰도 배지 + 경고 리스트 UI."
```

---

## 📤 산출물

### 생성될 파일
```
server/
├── video_validator.py            # 신규
├── analyzer/
│   └── quality_assessor.py       # 신규
├── tests/
│   ├── test_video_validator.py   # 신규
│   └── test_quality_assessor.py  # 신규
├── config.py                     # 상수 추가
├── analyzer/__init__.py          # run_full_analysis 통합
└── models/analysis_result.py     # confidence/warnings 필드

app/src/i18n/ko.json              # captureGuide 추가
app/src/screens/CameraScreen.tsx  # 가이드 모달
app/src/screens/ResultScreen.tsx  # 신뢰도 배지
```

### 다음 단계로 넘길 인터페이스

```python
class AnalysisResult(BaseModel):
    # ... 기존 ...
    confidence: Literal["high", "medium", "low"]
    warnings: list[QualityWarning]

class QualityWarning(BaseModel):
    code: str           # "HIGH_CADENCE_LOW_FPS" 등
    message_ko: str     # 사용자 표시용
```

---

## ⚠️ 흔한 함정

1. **fps 메타데이터 거짓말**
   - 일부 코덱/촬영 모드는 메타데이터 fps 와 실제 프레임 간격이 다름
   - `cv2.CAP_PROP_FPS` 와 `frame_count / duration` 둘 다 확인하고 큰 차이 시 후자 신뢰

2. **하드 요건을 너무 엄격하게**
   - 720p / 30fps 는 거의 모든 최신 스마트폰 기본 만족 → 이 정도면 적절
   - 더 올리면 진입 장벽만 높아지고 실제 정확도 개선은 미미

3. **경고가 너무 많이 떠서 사용자가 무시**
   - 4개 경고 코드는 의도적으로 적게 유지
   - 추가 경고 도입 전 실측 영상으로 false positive 율 확인

4. **신뢰도 "low" 가 너무 자주 나옴**
   - `CONFIDENCE_MEDIUM_MAX_WARNINGS` 를 충분히 크게 두지 않으면 대부분 low 가 됨
   - 실측 후 임계값 재조정

5. **검증 실패 메시지가 너무 기술적**
   - "FPS_TOO_LOW" 가 아니라 "프레임률이 너무 낮습니다" 로 표시
   - error_code 는 로깅/추적용, message_ko 는 사용자용으로 분리

6. **cadence 가 잘못 측정된 경우**
   - foot_strike_detector 의 false positive 가 cadence 를 부풀려 잘못된 경고를 띄울 수 있음
   - cadence ≥ 240 spm 처럼 명백히 비현실적인 값은 별도 경고 ("DETECTION_UNRELIABLE") 로 분리 검토

7. **앱에서 영상 다운스케일 후 fps 손실**
   - ffmpeg 다운스케일 시 원본 60fps → 30fps 로 떨어지면 의미 없음
   - PRD-5 의 ffmpeg 명령에 `-r 60` 명시 또는 원본 fps 보존 확인

8. **세로 영상이 "RESOLUTION_TOO_LOW" 로 잘못 안내됨** _(2026-05-15 실측에서 발견)_
   - 1080×1920 portrait 가 width 1080 < 1280 검사에서 거부되면 사용자는
     "더 고해상도로 촬영" 으로 오해 → 같은 세로 4K 로 재촬영해도 동일 거부.
   - `height > width` 체크를 **해상도 검사보다 먼저** 두고 `PORTRAIT_NOT_SUPPORTED`
     코드로 "휴대폰을 가로로 돌려 다시 촬영해주세요" 안내.
   - 가로/세로 동시 허용은 거부: 분석은 측면 횡방향 움직임이 본질이라 16:9 가
     정합. AR 가이드라인 두 종류 디자인 부담 + side_angle_deviation 회전 분기 회피.

---

## 🔗 PRD 간 영향

| 영향 받는 PRD | 변경 사항 |
|---|---|
| PRD-1 | `run_full_analysis` 시그니처 변경, AnalysisResult 확장 |
| PRD-4 (API) | 업로드 응답에 400 케이스 추가, 결과 스키마에 confidence/warnings |
| PRD-5 (앱 촬영) | 촬영 가이드 모달, ffmpeg 다운스케일 시 fps 보존 |
| PRD-6 (앱 결과) | 신뢰도 배지 + 경고 리스트 UI |
| PRD-7 (통합) | end-to-end 시나리오에 "거부된 영상" 케이스 추가 |

---

## 📚 학술 근거 / References

영상 사양 임계값은 (1) 모델(BlazePose) 의 권장 입력 + (2) 모션 캡처 sampling theory + (3) 러닝 cadence 통계 + (4) 측면 트레드밀 환경의 자체 검증을 종합한 결과이다.

### [V1] BlazePose 입력 해상도 (1280×720 최소)

- **Bazarevsky V, Grishchenko I, Raveendran K, Zhu T, Zhang F, Grundmann M.** BlazePose: On-device Real-time Body Pose Tracking. *arXiv:2006.10204.* 2020. (CV4ARVR Workshop, CVPR 2020.) [arXiv](https://arxiv.org/abs/2006.10204) — 모델 내부 256×256 입력 ROI 리사이즈를 사용. 원본 해상도가 720p 이하일 경우 ROI crop 후 픽셀 정보 손실로 HEEL/FOOT_INDEX 같은 작은 키포인트 정확도 급락. 720p (1280×720) 가 모바일 표준 + 모델 정확도 임계의 교차점.
- 가로 강제 (`PORTRAIT_NOT_SUPPORTED`): 분석이 sagittal plane 의 횡방향 움직임을 본질로 하므로 16:9 가로 영상에 최적화. AR 가이드라인이 가로 한 종류만 디자인되어 있고, side_angle_deviation 측정도 가로 영상 가정.

### [V2] 프레임률 (30fps 최소, 60fps 빠른 페이스 권장)

- **Nyquist sampling theorem**: 측정하려는 동작의 최고 주파수 ≥ fps/2. 러닝 cadence 180 spm = 3 Hz, foot strike 정확한 timestamp 식별엔 stance time(~200ms) 내 최소 6~10 샘플 필요 → 30 Hz 가 하한.
- **빠른 페이스 + 30fps 모션 블러**: cadence 200 spm × 1/30s 셔터 ≈ 한 프레임당 다리 스윙 30~40 cm 이동 → frame-to-frame 점프로 pose 추적 실패. PRD-8 함정 #5 와 일치.
- **Heiderscheit BC et al. 2011 MSSE** ([PRD-2 R1]) — 200 fps high-speed motion capture 기준이지만 임상 적용 시 60 fps 가 trade-off 임계로 자주 인용.

### [V3] 영상 길이 (5~60초)

- **하한 5초**: 안정적 비대칭 + 평균 지표 산출에 좌/우 각각 최소 5~7회 strike 필요. 6:00/km 페이스 cadence 170 spm × 5s ≈ 14 steps (좌/우 7씩). [Zifchock 2008 PRD-2 R5] 의 비대칭 통계 안정성 가이드 참조.
- **상한 60초**: 후처리 분석 elapsed time 제약 (Pose 추출 + 렌더링이 영상 길이 × ~10 배). BENCHMARK.md 측정치 (60fps 1080p 60s → ~10 분 분석) 와 UX 대기 한계의 교차점.

### [V4] 평균 visibility 임계 (0.6) 및 검출률 임계 (0.7)

- **Bazarevsky 2020 BlazePose** ([V1]) — `visibility` 출력은 frame 별 키포인트 검출 신뢰도 (0~1). 실험적으로 0.5 가 신뢰 가능/불가능 경계로 보고됨.
- 우리 임계 `VISIBILITY_THRESHOLD = 0.4` (분석 포함 vs 결측 처리), `WARN_LOW_AVG_VISIBILITY = 0.6` (저신뢰도 경고), `MIN_DETECTED_FRAME_RATIO = 0.7` (사후 경고)는 BlazePose 일반 권장 + 측면 트레드밀 자기-가림(self-occlusion) 환경 보정.

### [V5] Cadence 임계 (190 spm 빠른 페이스 경고)

- **Daniels J.** *Daniels' Running Formula.* 4th ed. Human Kinetics; 2021. (원판 1998) — 1984 LA Olympics 엘리트 러너 cadence 관측에서 ~180 spm 표준 제시 (단, 페이스 의존성).
- **Cavanagh PR, Kram R.** Stride length in distance running: velocity, body dimensions, and added mass effects. *Med Sci Sports Exerc.* 1989;21(4):467-479. — 개인별 economy 최적 stride frequency 가 존재함을 정량 검증.
- **Cavanagh PR, Williams KR.** The effect of stride length variation on oxygen uptake during distance running. *Med Sci Sports Exerc.* 1982;14(1):30-35. — preferred stride length 가 economy 와 최적 가까이 위치함.
- 우리 임계 190 spm: 일반 권장 180 + 안전 마진. 이 이상이면 [V2] 의 모션 블러 위험이 30fps 영상에서 dominant.

### [V6] 측면 촬영 보장 (양 어깨 x 거리 / 토르소 길이 임계 0.25)

- **Altman AR, Davis IS. 2012 Gait & Posture** ([PRD-2 R2]) — sagittal plane 측정 가정의 정확도 기반. 정면 촬영은 모든 sagittal 지표(무릎 굴곡, foot strike, overstride)의 정확도가 무너짐.
- 우리 임계 0.25: 양 어깨가 토르소 길이의 25% 이내로 겹쳐 보여야 측면 가정 유효. 자체 결정 — 정면 (>1.0) vs 측면 (≈0) 사이의 중간점 보수적 선택.
