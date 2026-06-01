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
# 30fps 기준 약 0.33초 → 사람이 1초에 3보 이상 같은 발로 디딜 수 없으므로 충분.
FOOT_STRIKE_COOLDOWN_FRAMES = 10


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
# 0.4 = lag ~2프레임(33ms @60fps), despiked 잔여 spike 진폭 약 40% 통과.
RENDER_SMOOTHING_ALPHA = 0.4


# =============================================================================
# 6. 무릎 굴곡 각도 (Knee Flexion)
# =============================================================================
# 착지 시점(IC, initial contact) hip-knee-ankle 벡터 내적 각도(°).
# 4단계: stiff_knee / borderline / good_flexion / over_bent
# Borderline 은 임계값 ±5° 이내일 때 우선 적용한다 (PRD-2 흔한 함정 #1).
# [Ref] Heiderscheit et al. 2011 MSSE (doi:10.1249/MSS.0b013e3181ebedf4) —
#       IC knee flexion 변동성 및 stiff knee 가 shock absorption 부족과 연결됨을
#       정량. 우리 측정 (180° = straight leg) 기준 정상 IC flexion ~20° → 160° 가
#       임상 통념의 stiff/normal 경계. 정확한 단일 정량 임계의 1차 출처는 부재
#       하며 본 임계는 임상 통념 + pace 4 영상 자체 검증 기반. PRD-2 §R1.
KNEE_STIFF_THRESHOLD = 160          # 이상 → Stiff Knee 🔴
KNEE_GOOD_MIN = 140                 # 정상 하한 🟢
KNEE_GOOD_MAX = 160                 # 정상 상한 🟢
KNEE_OVERBENT_THRESHOLD = 140       # 미만 → Over Bent 🟡
KNEE_BORDERLINE_TOLERANCE = 5       # 임계값 ±5° → borderline 🟡


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
VERTICAL_OSC_HIGH_THRESHOLD = 0.06  # 초과 → high_oscillation 🔴


# =============================================================================
# 10. 좌우 비대칭 (보조 지표)
# =============================================================================
# |L - R| / max(L, R) 이 이 값을 넘으면 경고.
# is_warning 트리거는 knee_angle 과 oscillation 두 지표에 한정한다.
# strike_count 비대칭은 측면 촬영의 far-side leg occlusion 노이즈가 dominant
# 신호이므로 단독 트리거에서 제외하고, 결과 객체에 ratio 만 정보성으로 노출한다
# (4 pace 영상 같은 동일 러너 정상 자세에서 strike diff 3 false positive 다발 확인,
# 2026-05-16). 진짜 비대칭(절뚝/비스듬런) 은 knee 또는 osc 에 동시에 신호가 잡힌다.
# [Ref] Zifchock et al. 2008 Gait Posture (doi:10.1016/j.gaitpost.2007.08.006) —
#       Symmetry Index 정량 방법론. Pappas et al. 2015 Hum Mov Sci 40:273-283
#       (PMID:25625812) — healthy 러너 자연 ASI 1.81~6.38% → 10% 가 healthy 분포
#       너머의 임상 의미. Parkinson et al. 2021 J Sports Sci Med 20(4):594-617
#       (DOI:10.52082/jssm.2021.594) systematic review — 10~15% 임계가 후속 임상
#       문헌의 합의된 채택 범위. PRD-2 §R5/§R6 (자체 검증 포함).
ASYMMETRY_WARNING_THRESHOLD = 0.1   # 10%

# 좌/우 발 평균 visibility 차이가 이 값을 초과하면 strike_count_ratio 를 NaN 으로
# 대체한다 — 한쪽 발이 occlusion 으로 검출 신뢰도가 낮으면 strike count 차이가
# 실제 비대칭이 아닌 검출 누락일 가능성이 높기 때문 (사용자에게도 NaN 으로 노출되어
# 신뢰할 수 없는 신호임을 명시).
# [Ref] BlazePose paper (Bazarevsky 2020) — visibility 출력은 키포인트 검출
#       신뢰도. PRD-2 §R6 (자체 검증 데이터 + 이론적 배경).
ASYMMETRY_FOOT_VIS_DIFF_THRESHOLD = 0.10


# =============================================================================
# 11. 입력 영상 사양 (PRD-8)
# =============================================================================
# 분석 알고리즘(MediaPipe heavy + Hampel + One Euro) 은 자체 정확도 천장에 도달했고,
# 30fps 미만에서는 착지 순간 표본이 부족해 스켈레톤 추적과 foot strike 판정이
# 불안정하다. MVP 접근성을 위해 30fps 이상은 허용하되, 빠른 페이스 + 저fps 조합은
# 소프트 경고로 안내한다.

# === 하드 요건 (미충족 시 분석 거부) ===
# [Ref] PRD-8 §V1 (해상도, BlazePose 입력 ROI 정확도) /
#       §V2 (fps, Nyquist sampling + 모션 블러 / Heiderscheit 2011) /
#       §V3 (길이, Zifchock 통계 안정성 + BENCHMARK.md elapsed).
MIN_VIDEO_WIDTH = 1280
MIN_VIDEO_HEIGHT = 720
MIN_VIDEO_FPS = 30
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


# =============================================================================
# 12. 추가 폼 지표 (측면 영상 기반)
# =============================================================================
# MVP v2 확장 지표. 모두 단일 측면 영상에서 비교적 안정적으로 산출 가능한
# 2D proxy 이며, 부상 판정보다는 코칭/폼 개선을 우선한다.

# 착지 시 정강이 기울기: ankle→knee 벡터가 화면 세로축에서 벗어난 각도.
# 값이 클수록 착지 순간 발이 무릎보다 앞에 있거나 정강이가 과하게 누운 상태.
TIBIA_OVERREACH_THRESHOLD = 12.0

# 몸통 기울기: 골반 중앙→어깨 중앙 벡터의 세로축 기준 절대 각도.
# 러닝에서는 약간의 전경사가 자연스럽지만 25° 이상은 과한 숙임/젖힘 가능성.
TORSO_LEAN_LOW_THRESHOLD = 3.0
TORSO_LEAN_HIGH_THRESHOLD = 25.0

# 팔꿈치 각도: shoulder-elbow-wrist 내각. 너무 작으면 팔이 접혀 긴장, 너무 크면
# 팔이 펴져 리듬 손실 가능성.
ARM_ELBOW_MIN_GOOD = 70.0
ARM_ELBOW_MAX_GOOD = 115.0

# 머리 전방 위치: 코/귀 중앙과 어깨 중앙의 수평 거리 ÷ torso length.
# 측면 방향을 자동 판별하기 어렵기 때문에 절대값 proxy 로 사용한다.
HEAD_FORWARD_RATIO_THRESHOLD = 0.22

# === 신뢰도 등급 (경고 개수 기반) ===
CONFIDENCE_HIGH_MAX_WARNINGS = 0       # 0개 → high
CONFIDENCE_MEDIUM_MAX_WARNINGS = 2     # 1~2개 → medium, 3개+ → low
