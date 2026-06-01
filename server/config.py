"""
프로젝트 전역 상수 및 임계값 정의 파일.

⚠️ 모든 임계값은 반드시 이 파일에서만 관리합니다.
   코드 내 매직 넘버 사용 금지 (PRD-0 Vibe Coding 절대 원칙 #1).

참고:
    - PRD-0-context.md  : 절대 준수 제약 사항 및 색상 코딩
    - PRD-1-pose-pipeline.md : MediaPipe / 전처리 / 착지 판별 임계값
"""

# =============================================================================
# 1. MediaPipe Pose 설정
# =============================================================================
# 후처리 분석이므로 정확도를 최우선으로 한다. CPU에서 느리지만 허용 범위 내.
# (PRD-0 절대 준수 제약: model_complexity=2 고정, 0/1 사용 금지)
# [Ref] Bazarevsky et al. 2020 BlazePose (arXiv:2006.10204) — PRD-2 §R7, PRD-8 §V1.
MEDIAPIPE_MODEL_COMPLEXITY = 2

# 검출/추적 신뢰도 하한. 측면 트레드밀 환경에서 0.5가 안정적.
MEDIAPIPE_MIN_DETECTION_CONFIDENCE = 0.5
MEDIAPIPE_MIN_TRACKING_CONFIDENCE = 0.5

# visibility가 이 값 미만이면 결측(NaN)으로 처리한다.
# PRD-1은 0.5를 '권장' 했으나, 측면 트레드밀의 상수적 자기-가림
# (앞다리에 의한 뒷다리 occlusion)으로 인해 0.4 로 완화.
# 디버그 영상에서 한쪽 다리 스켈레톤이 끊기는 현상 확인 후 조정.
VISIBILITY_THRESHOLD = 0.4


# =============================================================================
# 2. 전처리 (Forward Fill + EMA)
# =============================================================================
# 결측 구간이 이 프레임 수를 초과하면 NaN 유지 → 해당 구간 분석 제외.
# 30fps 기준 약 0.33초. Occlusion이 더 길면 신뢰할 수 없는 추정으로 본다.
MAX_FORWARD_FILL_FRAMES = 10

# Exponential Moving Average 평활화 계수.
# 작을수록 더 부드럽지만 반응 지연. 0.3은 jitter 제거 + 착지 시점 유지의 균형점.
EMA_ALPHA = 0.3

# === Hampel 필터 (단일 프레임 spike 제거) ===
# mediapipe 의 1프레임 mislocalization 을 통계적 outlier 로 감지/대체한다.
# window 중간값 ± k * 1.4826 * MAD 를 정상 범위로 정의.
# 30fps 기준 5프레임 ≈ 167ms. 빠른 다리 스윙도 이 구간 안에서는 큰 outlier 가 흔치 않음.
HAMPEL_WINDOW = 5            # 홀수. 중심 좌우 ± (HAMPEL_WINDOW // 2)
HAMPEL_THRESHOLD_K = 3.0     # 3-sigma 등가 (정규분포 가정 시)


# === One Euro Filter (적응형 평활화, EMA 대체) ===
# Casiez et al. 2012. MediaPipe / Apple Vision / Plask 등 상용 표준.
# 정지 시 강한 평활화, 빠른 동작 시 lag 0.
#     cutoff = min_cutoff + beta * |velocity|
# 측면 트레드밀에서는 다리 스윙이 빠르므로 beta 를 약간 높여 lag 최소화.
ONE_EURO_MIN_CUTOFF = 1.5    # Hz. 작을수록 더 부드럽지만 lag 증가.
ONE_EURO_BETA = 0.10         # 속도 적응 강도.
ONE_EURO_D_CUTOFF = 1.0      # 도함수 추정용 cutoff.


# === 좌/우 Identity 보정 ===
# 측면 자기-가림에서 mediapipe 가 좌/우 다리 landmark 를 혼동하는 경우 보정.
# 러닝 cyclic motion 특성상 nearest-neighbor 만으로는 over-correcting 되므로 매우
# 보수적 임계값을 사용. 비율 + 절대 게인 두 조건을 AND 로 둔다.
LR_SWAP_MIN_GAIN = 0.10      # swap 으로 평균 거리가 이 값 이상 감소해야 (정규화 좌표).
LR_SWAP_RATIO = 0.4          # swap_cost / normal_cost 가 이 값 이하여야.


# =============================================================================
# 3. Foot Strike (착지) 판별
# =============================================================================
# 동일 발 착지 중복 판정 방지를 위한 최소 프레임 간격.
#
# 60fps 기준 20 프레임 = 0.333초. 정상 stride cycle (180 spm 양발 합산
# baseline → 한 발 cycle 60/(180/2) ≈ 0.667초) 의 절반.
#
# [실측 보정 2026-05-29] 기존 10프레임 (0.167s) 은 한 stance phase 안의
# pose 노이즈/발목 미세 oscillation 에 의한 double peak 를 막지 못해
# 측정 cadence 가 +10~28% over-count 됐다. 4영상 (pace530/6/630/7) ground
# truth 카운트 (25/67/45/33) 대비 cd=20~40 plateau 에서 정확 매치 (pace630
# 만 +3 잔여, prominence 임계 별도 검토). cd=20 은 plateau 의 보수적 경계
# 로 정상 strike 손실 위험 0, 실측에서 검증된 안전 마진.
#
# [Ref] Cavanagh & Kram 1989 MSSE 21(4):467-479 — 정상 stride cycle 시간.
#       Daniels 2021 — 180 spm baseline.
FOOT_STRIKE_COOLDOWN_FRAMES = 20

# 정규화 좌표상 peak prominence 의 최소 임계.
# [실측 보정 2026-05-29] pose extraction boundary (NaN sentinel 마스킹 영역
# 직후) 의 spurious peak (prom 0.0001 ~ 0.0007) 가 정상 strike (prom 0.04 ~
# 0.09, median ≈ 0.07) 와 100배 차이로 분리된다. 4영상 sweep 결과
# 0.001 이 spurious 만 거르고 정상 strike 손실 0 인 보수적 임계 (4영상
# 총 절대오차 5→3 로 감소: pace530 0/pace6 0/pace630 +2/pace7 -1).
# 0.001 = 정규화 좌표 화면 높이의 0.1% = 1080p 에서 약 1.1픽셀 (pose
# estimation noise floor 수준의 미세 변위).
FOOT_STRIKE_MIN_PROMINENCE = 0.001


# =============================================================================
# 4. 색상 코딩 (OpenCV는 BGR 순서!)
# =============================================================================
# 🟢 정상 범위
COLOR_SAFE_BGR = (94, 197, 34)      # #22C55E
# 🟡 주의 필요
COLOR_WARNING_BGR = (8, 179, 234)   # #EAB308
# 🔴 부상 위험 / 즉시 교정 필요
COLOR_DANGER_BGR = (68, 68, 239)    # #EF4444


# =============================================================================
# 5. 영상 처리
# =============================================================================
# 앱에서 720p로 다운스케일하여 업로드한다는 전제.
TARGET_FPS = 30
TARGET_RESOLUTION = (1280, 720)  # (width, height)


# === 렌더링 가시화 전용 평활화 (PRD-3 흔한 함정 #11 후속) ===
# despiked 좌표는 lag 0 이지만 mediapipe 자체의 inter-frame jitter 가 남아 있다.
# 분석 파이프라인의 One Euro filter 는 분석용 df 만 평활화하므로, 가시화 직전에
# 별도의 약한 EMA 를 한 번 더 적용한다.
#   y_t = α·x_t + (1-α)·y_{t-1}
# α 가 클수록 lag ↓ / jitter 남음. EMA_ALPHA(0.3, 분석용) 보다 명확히 크게 두어
# 가시 lag 을 1~2 프레임(33~66ms) 수준으로 제한. 1.0 = 평활화 OFF.
RENDER_SMOOTHING_ALPHA = 0.6


# =============================================================================
# 6. 무릎 굴곡 각도 (Knee Flexion)
# =============================================================================
# 착지 시점(IC, initial contact) hip-knee-ankle 벡터 내적 각도(°).
# 4단계: stiff_knee / borderline / good_flexion / over_bent
# Borderline 은 임계값 ±3° 이내일 때 우선 적용한다 (PRD-2 흔한 함정 #1).
# [Ref] Heiderscheit et al. 2011 MSSE (doi:10.1249/MSS.0b013e3181ebedf4) —
#       n=45 healthy recreational runner 의 preferred condition IC knee flexion
#       baseline = 17.8° ± 4.0° (논문 본문 보고값). Heiderscheit 컨벤션 (0° =
#       straight leg) ↔ 우리 컨벤션 (180° = straight leg) 변환:
#         knee angle 162.2° = IC flexion 17.8° = baseline mean
#         knee angle 165°   = IC flexion 15°   = mean − 0.7 SD (stiff 임계)
#         knee angle 140°   = IC flexion 40°   = mean + 5.6 SD (over_bent 임계)
#       우리 stiff 임계 165° 는 baseline 평균보다 약 0.7 SD stiffer 영역 — 통계적
#       outlier-leaning 위치. 자체 데이터: pace 530/6/7/630 200 strikes 평균
#       knee angle 158.5° (baseline + 0.9 SD 더 굽힘 — 숙련 러너 일관 신호),
#       max 164°, > 165° 0건, < 140° 0건. False positive 0건 검증.
#       2026-05-25 재조정 (160→165, tol 5→3) 이전 임계는 분포 모드 [158,160)
#       정점을 가로질러 94.5% borderline 라벨링되며 신호 가치 상실.
#       향후 작업: Peak Flexion (mid-stance) 측정 추가 시 Souza 2016 PMR
#       (PMC4714754) 의 "<45° flexion = stiff" 가 1차 근거 예정. 현재는 IC 만
#       평가. PRD-2 §R1 + §[R1-future].
KNEE_STIFF_THRESHOLD = 165          # 이상 → Stiff Knee 🔴
KNEE_GOOD_MIN = 140                 # 정상 하한 🟢
KNEE_GOOD_MAX = 165                 # 정상 상한 🟢
KNEE_OVERBENT_THRESHOLD = 140       # 미만 → Over Bent 🟡
KNEE_BORDERLINE_TOLERANCE = 3       # 임계값 ±3° → borderline 🟡


# =============================================================================
# 7. Foot Strike 각도
# =============================================================================
# 발뒤꿈치(HEEL) → 발끝(FOOT_INDEX) 벡터의 수평 기울기(°), 진행 방향 무관.
# (analyzer/metrics/foot_strike.py 의 module docstring 참조)
# 양수: 발끝이 발뒤꿈치보다 위 (dorsiflexion) → heel strike 경향
# 음수: 발끝이 발뒤꿈치보다 아래 (plantarflexion) → forefoot 경향
# [Ref] Altman & Davis 2012 Gait Posture (doi:10.1016/j.gaitpost.2011.09.104)
#       — FSA>0=RFS / <0=FFS/MFS 분류 표준 (0° cutoff). Lieberman et al. 2010
#       Nature (doi:10.1038/nature08723) — RFS 충격 부하/부상 위험.
#       ±3° 마진은 2D 영상 perspective + 발 길이 정규화 노이즈 안전 마진 —
#       임상 분류 관행과 정합 (자체 결정, 2026-05-17 보수적 축소). PRD-2 §R2.
HEEL_STRIKE_THRESHOLD = 3           # 초과 → heel_strike 🔴
FOREFOOT_STRIKE_THRESHOLD = -3      # 미만 → forefoot_strike 🟡
# (이 사이는 mid_foot_strike 🟢)


# =============================================================================
# 8. 오버스트라이딩 (Overstriding)
# =============================================================================
# 착지 시 발목 X 가 골반 X 보다 얼마나 앞에 있는지 (정규화 좌표).
# [Ref] Heiderscheit et al. 2011 MSSE — step length 감소가 hip/knee loading 동시
#       감소. Schubert et al. 2014 Sports Health (doi:10.1177/1941738113508544) —
#       overstride 조건에서 무릎 신전 모멘트/rearfoot 각속도 유의 증가. PRD-2 §R3.
OVERSTRIDE_THRESHOLD = 0.15         # 초과 → over_stride 🔴, 이하 → good_stride 🟢


# =============================================================================
# 9. 수직 진폭 (Vertical Oscillation)
# =============================================================================
# 1 Stride (동일 발 연속 착지) 동안의 골반 Y max-min (정규화 좌표).
# [Ref] Tartaruga et al. 2012 RQES (doi:10.1080/02701367.2012.10599870) +
#       Folland et al. 2017 MSSE (doi:10.1249/MSS.0000000000001245) — VO 가
#       running economy 의 핵심 modifiable 변수. Healthy 범위 6~10cm
#       (Cavanagh & Williams 1982 MSSE PMID:7070254). 신장 1.7m + PRD-8 촬영
#       가이드(인체 화면 60~80% 점유) 기준 정규화 0.06 ≈ 10cm (healthy upper
#       bound). 2026-05-17 보수적 임계 0.08 → 0.06 으로 학술 통념에 정렬. PRD-2 §R4.
VERTICAL_OSC_HIGH_THRESHOLD = 0.06  # 초과 → high_oscillation 🔴 (fallback: 신장 미입력 시)

# === cm-aware 모드 (Phase 1, 2026-05-28) ===
# 신장(height_cm) + 프레임 내 신체 정규화 길이(nose~ankle median) 환산으로
# 정규화 임계의 프레이밍 의존성을 제거하고 절대 cm 단위 임계를 적용한다.
#     scale_cm_per_norm = height_cm / body_norm_length
#     vo_cm = vo_norm * scale_cm_per_norm
# height_cm 미입력 또는 body_norm_length 추정 실패 시 VERTICAL_OSC_HIGH_THRESHOLD
# 정규화 임계로 fallback (frame 60~80% 점유 가정 유지).
# [Ref] Cavanagh & Williams 1982 MSSE PMID:7070254 — running economy 최적 VO 6~10cm.
VO_HIGH_THRESHOLD_CM = 10.0


# =============================================================================
# 11. 입력 영상 사양 (PRD-8)
# =============================================================================
# 분석 알고리즘(MediaPipe heavy + Hampel + One Euro) 은 자체 정확도 천장에 도달했고,
# 4'/km 이상의 빠른 페이스 + 30fps 환경에서 모션 블러 + 프레임 간 점프로 인해
# 스켈레톤 추적이 실패하는 현상이 관측됨. 알고리즘이 아닌 입력 정보량의 한계이므로
# 영상 사양 자체에 가드레일을 둔다.

# === 하드 요건 (미충족 시 분석 거부) ===
# [Ref] PRD-8 §V1 (해상도, BlazePose 입력 ROI 정확도) /
#       §V2 (fps, Nyquist sampling + 모션 블러 / Heiderscheit 2011) /
#       §V3 (길이, Zifchock 통계 안정성 + BENCHMARK.md elapsed).
MIN_VIDEO_WIDTH = 1280
MIN_VIDEO_HEIGHT = 720
MIN_VIDEO_FPS = 60
MIN_VIDEO_DURATION_SEC = 5
MAX_VIDEO_DURATION_SEC = 60
# 분석 가능 프레임 비율 하한 (사람이 검출된 프레임 / 전체 프레임).
# 사후 검증 (mediapipe 결과 기반) 이므로 soft warning 으로 분류.
MIN_DETECTED_FRAME_RATIO = 0.70

# === 소프트 경고 임계값 ===
# 빠른 페이스 + 저fps 조합 경고.
# 30fps × 200 spm = 1보당 9프레임 → 착지 시점 모호 + 모션 블러 심각.
# [Ref] Daniels' Running Formula 4ed (Human Kinetics 2021) — 180 spm 엘리트 표준.
#       Cavanagh & Kram 1989 MSSE 21(4):467-479 — 개인별 economy 최적 stride freq.
#       PRD-8 §V5.
WARN_HIGH_CADENCE_SPM = 190         # 이 이상이면서 fps<60 이면 경고
WARN_FPS_FOR_HIGH_CADENCE = 60      # 이 fps 미만 + 빠른 cadence → 경고

# 평균 visibility 가 이 값 미만이면 가림/저조도/loose clothing 경고.
WARN_LOW_AVG_VISIBILITY = 0.60

# 측면 각도 이탈 판정: 양 어깨 x 거리 / 토르소 세로 길이.
# 측면 촬영이면 양 어깨가 거의 겹쳐 비율 → 0, 정면이면 크게 벌어짐.
# [Ref] Altman & Davis 2012 Gait Posture — 모든 sagittal plane 측정의 정확도가
#       측면 촬영 가정에 의존. PRD-8 §V6.
WARN_SIDE_ANGLE_DEVIATION = 0.25

# 카메라 흔들림: 배경 영역의 frame-to-frame optical flow 평균 픽셀.
# (현재 미사용. 추후 quality_assessor 확장 시 사용.)
WARN_CAMERA_SHAKE_PIXELS = 3.0

# === 신뢰도 등급 (경고 개수 기반) ===
CONFIDENCE_HIGH_MAX_WARNINGS = 0       # 0개 → high
CONFIDENCE_MEDIUM_MAX_WARNINGS = 2     # 1~2개 → medium, 3개+ → low


# =============================================================================
# 12. Cadence pace-aware 보정 (Phase 0, 2026-05-28)
# =============================================================================
# 사용자 입력 pace (sec/km) + height (cm) 로 개인별 기대 cadence 범위 산출.
# 단일 "180 spm" cutoff 는 (a) pace 가 빠를수록 cadence 자연 상승, (b) 키 큰
# 사람은 stride 길어 같은 pace 에 더 낮은 cadence 가 정상 — 두 효과 무시.
#
# 밴드는 신장 170cm 기준 명목 범위 (lo, hi). 신장 보정:
#   shift_spm = -(height_cm - 170) * CADENCE_HEIGHT_SHIFT_SPM_PER_CM
# (키 ↑ → expected ↓; 키 ↓ → expected ↑)
#
# Pace 미입력 시 expected_range = None → coach trailing 생략, summary 의
# cadence_spm 만 정보성으로 노출 (기존 동작 유지).
#
# [Ref] Daniels' Running Formula 4ed (Human Kinetics 2021) — 180 spm 엘리트
#       표준 + pace 별 자연 증가. Hunter et al. 2017 J Sports Sci 35(15):1488-1495
#       (DOI:10.1080/02640414.2016.1228562) — pace 와 cadence 의 양의 회귀.
#       Schubert et al. 2014 Sports Health (PRD-2 §R3) — stride freq 와 mechanics.
#       Cavanagh & Kram 1989 MSSE 21(4):467-479 — 개인별 economy 최적 stride freq.
#       Winter 1990 — leg length ≈ height × 0.485.
CADENCE_BANDS_170CM: tuple[tuple[float, float, int, int], ...] = (
    # (pace_min_sec_per_km inclusive, pace_max_sec_per_km exclusive, spm_lo, spm_hi)
    (390.0, float("inf"), 162, 175),   # >= 6:30/km — 조깅
    (330.0, 390.0,        168, 180),   # 5:30 ~ 6:30
    (270.0, 330.0,        175, 188),   # 4:30 ~ 5:30
    (0.0,   270.0,        182, 196),   # < 4:30 — tempo/race
)
CADENCE_HEIGHT_SHIFT_SPM_PER_CM = 0.5  # +1cm 신장 → -0.5 spm 기대치

# 측정 cadence 가 expected_range 밖 → hint 분류. deviation_pct 는 가장 가까운
# 경계 대비 백분율 (low/high), optimal 이면 0.
CADENCE_HINT_OPTIMAL = "optimal"
CADENCE_HINT_LOW = "low"
CADENCE_HINT_HIGH = "high"
