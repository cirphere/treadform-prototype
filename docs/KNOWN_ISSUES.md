# 알려진 이슈

## Critical

(현재 없음)

## Warnings

### W-001: 동시 3개 이상 분석 시 CPU 포화

- **증상**: 4번째 요청부터 처리 시간이 급격히 증가.
- **원인**: MediaPipe Pose 가 CPU 멀티코어를 최대 활용.
- **워크어라운드**: 서버 측 큐잉 (Phase 2 에서 Celery 도입 예정).

### W-002: iOS 시뮬레이터에서 카메라 미지원

- **증상**: 시뮬레이터에서 촬영 화면이 검은색.
- **원인**: iOS 시뮬레이터 일반적 제약.
- **워크어라운드**: 실기기에서 테스트.

### W-003: 빠른 페이스(4'/km, ≥190 spm) + 30fps 영상의 스켈레톤 추적 저하

- **증상**: 다리 스윙 구간에서 mediapipe 가 한 프레임씩 놓치거나 좌/우 혼동.
- **원인**: 30fps × 200 spm = 1보당 9프레임. 모션 블러 + 프레임 간 점프.
- **워크어라운드 (PRD-8)**: `HIGH_CADENCE_LOW_FPS` 경고 + 60fps 권장 안내. confidence=medium.
- **근본 해결**: 사용자가 60fps 로 재촬영 (대부분의 최신 스마트폰 지원).

### W-004: Android 에뮬레이터 갤러리 picker 가 sdcard 영상을 못 보임

- **증상**: image-picker 가 emulator 의 갤러리 인덱싱 캐시 문제로 항목 표시 실패.
- **워크어라운드**: 파일에서 찾기 (SAF, @react-native-documents/picker) 사용 — videoPicker.ts 참고.

### W-005: RN 0.85 + axios v1.16 multipart 비호환

- **증상**: `axios.post(/upload, FormData)` 가 `ERR_NETWORK` 와 함께 OkHttp 의 `multipart != application/x-www-form-urlencoded` 예외 발생.
- **원인**: axios v1.16 의 transformRequest 가 RN 의 `{uri,type,name}` blob descriptor 를 인식 못 함 → `application/x-www-form-urlencoded` 폴백 → OkHttp 가 거부.
- **해결**: `uploadVideo` 만 XMLHttpRequest 로 분리 (그 외 JSON 엔드포인트는 axios 유지). `src/services/api.ts` 의 XhrUploadError 분기 참고.

### W-006: @react-native/gradle-plugin foojay-resolver Gradle 9 비호환

- **증상**: `foojay-resolver 0.5.0` 가 Gradle 9 빌드 시 클래스 missing 오류.
- **해결**: `patch-package` 로 0.5.0 → 1.0.0 패치 영속화. `app/patches/@react-native+gradle-plugin+0.85.3.patch` 참고.

## Minor

### M-001: 720p 변환 시 음성 제거됨

- **상태**: 의도된 동작.
- **이유**: 분석에 불필요하며 파일 크기 절약.

### M-002: 한글 폰트 자동 탐색이 일부 시스템에서 실패

- **워크어라운드**: 시스템에 NanumGothic 설치 또는 폰트 경로 수동 지정.

### M-003: 세로 영상 거부 시 사용자 혼란

- **상태**: 의도된 동작 (PRD-8).
- **이유**: 분석은 측면 횡방향 움직임이 본질 → 가로(16:9) 정합.
- **완화**: captureGuide 모달로 사전 안내 + CameraScreen 가로 강제.

### M-004: `run_full_analysis_with_output` 메모리 — raw_df 캐싱 후에도 큰 영상은 1GB+ 사용

- **상태**: 단일 분석 기준 정상. 동시 처리 시 호스트 메모리 압박 가능.
- **워크어라운드**: 동시 2개까지 권장. concurrent_3 벤치마크 참고.

### M-005: Gradle / Kotlin compile daemon 이 idle 상태에서 1~2GB 점유 유지

- **상태**: Gradle 의 기본 동작 (autoshutdown 7200초).
- **워크어라운드**: 빌드 직후 `gradlew --stop` 또는 daemon 프로세스 직접 종료.
