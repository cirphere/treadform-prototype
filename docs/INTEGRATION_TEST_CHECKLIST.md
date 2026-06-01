# 통합 테스트 체크리스트 (PRD-7)

각 시나리오마다 수동 검증 후 □ → ☑ 로 채운다. 자동화 가능한 부분은 명시.

## 사전 준비

- [x] 서버 실행: `venv\Scripts\python -m uvicorn main:app --host 0.0.0.0 --port 8000`
- [x] PC IP / 방화벽 8000 인바운드 허용 (에뮬 검증 시 `adb reverse tcp:8000 tcp:8000` 으로 대체 가능)
- [x] 앱 빌드: 에뮬레이터 또는 실기기 (`gradlew app:installDebug`)
- [x] `app/src/constants/api.ts` BASE_URL 일치 (에뮬: 10.0.2.2 / 실기기: LAN IP)
- [x] 샘플 영상 5종 (good pose, bad pose, member-cum × 3) + 거부 영상 6종 + 저신뢰도 2종 준비 — 거부 영상 6종은 `server/tests/reject_samples/` 에 cv2 합성 자동화로 확보, 저신뢰도 영상은 미확보 (시나리오 7 deferred)

## 시나리오 1: 일반 사용자 단독 사용

- [ ] 앱 시작 → HomeScreen (한국어, 모드 OFF, 회원 미선택)
- [ ] "촬영 시작" → 가로 강제 + AR 가이드 표시
- [ ] 10초 녹화 → Upload 화면 자동 진입
- [ ] 진행률 표시 (0~100%)
- [ ] 분석 완료 (~30~40초) → ResultScreen 자동 진입
- [ ] 렌더링 영상 재생 (스켈레톤 오버레이)
- [ ] Danger 마커가 타임라인에 표시
- [ ] 영상 재생이 Danger 구간 진입 시 0.5x 슬로우 자동 전환
- [ ] 코칭 메시지 카드 (자연스러운 한국어)
- [ ] 4대 지표 + 비대칭 배지 표시 (색상 정확)
- [ ] 신뢰도 배지 (high → 녹색)

## 시나리오 2: 트레이너의 신규 회원 등록 + 첫 분석

- [ ] ModeToggle ON → 트레이너 모드
- [ ] "회원 선택" → MemberSelect → "회원 추가" → "홍길동" 입력 → 등록
- [ ] 등록 후 회원 자동 선택
- [ ] 홈에서 "누적 대시보드 보기" 링크 노출
- [ ] 촬영 → 업로드 (member_id 자동 포함, 서버 로그 확인)
- [ ] 결과 화면 진입
- [ ] DashboardScreen 진입 → "분석 이력이 없습니다" 가 아닌 1회 데이터 (값 부족 시 "비교 데이터가 부족합니다" 정상)

## 시나리오 3: 트레이너 회원 누적 데이터 시각화

- [ ] 동일 회원으로 3회 이상 분석 (서로 다른 영상)
- [ ] DashboardScreen → cadence / danger / 비대칭 3개 라인 차트 표시
- [ ] X 축 1회/2회/3회 시간순 정렬
- [ ] 데이터 포인트 누락 없음
- [ ] PT 효과 요약 텍스트 (예: "첫 회 5회 → 최근 2회로 위험 구간이 감소했습니다")

## 시나리오 4: 모드 전환 무결성

- [ ] 트레이너 모드 ON → 회원 A 선택 → 분석
- [ ] 모드 OFF (일반) → 본인 분석 (member_id 없이 업로드, 서버 로그 확인)
- [ ] 모드 ON → 회원 B 선택 → 분석
- [ ] A 의 대시보드에 B 의 결과가 섞이지 않음 (history API 검증)
- [ ] AsyncStorage 정상 영속화 (앱 재시작 후 모드 + 선택 회원 유지)

## 시나리오 5: 네트워크 장애 복구

- [ ] 촬영 후 업로드 직전 WiFi OFF
- [ ] "서버에 연결할 수 없습니다" 한국어 에러 모달
- [ ] WiFi 재연결 후 "다시 시도" 버튼 동작 → 정상 업로드
- [ ] 분석 중 (Processing) WiFi 끊김 → 폴링 실패 → 재연결 시 폴링 재개
- [ ] 앱 크래시 없음

## 시나리오 6: 거부 영상 처리 (PRD-8)

### 서버 측 자동 검증 (완료)

```powershell
Set-Location server
venv\Scripts\python -m pytest tests\test_video_rejection_e2e.py -v
```

→ 6 passed. 합성된 영상은 `server/tests/reject_samples/` 에 캐시 (앱 수동 검증에 그대로 활용).

### 앱 측 수동 검증

합성된 영상을 에뮬레이터로 푸시:
```powershell
$src = "C:\vibeRun\server\tests\reject_samples"
adb push $src\portrait_720x1280.mp4 /sdcard/Download/
adb push $src\low_res_640x480.mp4   /sdcard/Download/
adb push $src\low_fps_24fps.mp4     /sdcard/Download/
adb push $src\duration_3s.mp4       /sdcard/Download/
adb push $src\duration_65s.mp4      /sdcard/Download/
adb push $src\corrupt.mp4           /sdcard/Download/
adb shell am broadcast -a android.intent.action.MEDIA_SCANNER_SCAN_FILE -d file:///sdcard/Download
```

각 영상 앱 업로드 검증 (2026-05-16 검증 완료):

- [x] portrait.mp4 → **클라이언트 사전 차단** `home.portraitNotSupported` 모달 (갤러리 picker 의 width<height 검사, PRD-8 함정 #9 — 서버 호출 없이 차단). SAF picker 사용 시에만 서버 도달 + `PORTRAIT_NOT_SUPPORTED`.
- [x] low_res.mp4 → 400 + `RESOLUTION_TOO_LOW` + 한국어 모달
- [x] low_fps.mp4 → 400 + `FPS_TOO_LOW` + 한국어 모달
- [x] short.mp4 → 400 + `DURATION_TOO_SHORT` + 한국어 모달
- [x] long.mp4 → 400 + `DURATION_TOO_LONG` + 한국어 모달
- [x] corrupt.mp4 → 400 + `CANNOT_OPEN_VIDEO` + 한국어 모달 (SAF picker 필요 — 갤러리 picker 는 33 byte 영상을 미디어로 인식 못 함)
- [x] 모든 거부 케이스에서 mediapipe 호출 없음 (validator 단계에서 차단)
- [x] 거부된 영상이 `server/storage/uploads/` 에 남지 않음 (정상 분석분 2건만 신규)
- [x] 모달의 "다시 시도" / "홈으로 돌아가기" 동작 확인

## 시나리오 7: 저신뢰도 (low confidence) UX (PRD-8) — **deferred (저신뢰도 샘플 영상 미확보, 2026-05-16)**

- [ ] 빠른 페이스 30fps 영상 → confidence=medium + 경고 카드 1~2건
- [ ] 어두운 조명 + 헐렁한 옷 영상 → confidence=low + 경고 카드 3건+
- [ ] medium: 신뢰도 배지 노랑 ("보통") + 메트릭 정상 톤
- [ ] low: 신뢰도 배지 빨강 ("낮음") + 메트릭/코칭 영역 opacity 0.4 (톤다운) + "참고용" 배너
- [ ] WarningList 는 톤다운 외부 (또렷이 보임)
- [ ] warnings 가 빈 배열이면 WarningList 미표시
- [ ] 렌더링 영상에도 좌상단 신뢰도 배지 합성 (PRD-3)

## 회귀

- [ ] `cd server; venv\Scripts\python -m pytest -q` → 154 passed (148 단위 + 6 거부 E2E)
- [ ] `cd server; venv\Scripts\python -m pytest tests\test_benchmark.py -v -s -m benchmark` → 모두 통과 + 시간 제한 내
