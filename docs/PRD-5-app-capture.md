# PRD-5: 앱 - 촬영 & 업로드 플로우

> 📍 항상 함께 참조: **[PRD-0-context.md](./PRD-0-context.md)**
> 📍 이전 단계 산출물: **[PRD-4-api.md](./PRD-4-api.md)**
> 📍 교차 참조: **[PRD-8-video-input-spec.md](./PRD-8-video-input-spec.md)** (촬영 가이드 텍스트, 가로 강제, fps 보존)

---

## 🎯 이 단계의 목표

React Native 앱에서 **AR 가이드라인 오버레이로 촬영 → 720p 다운스케일 → 서버 업로드 → 분석 진행 폴링**까지의 전체 플로우를 완성한다. 트레이너 모드 토글 및 회원 선택 UI 포함.

**PRD-8 연계**: 사용자가 영상을 찍기 전에 본 PRD 의 모든 촬영 가이드(가로, 측면, 거리, 의상)를 모달로 보여줘서 업로드 후 거부당하는 UX 손실을 사전에 차단한다.

---

## 📥 입력 (의존성)

- **이전 단계 산출물**: FastAPI 서버 (`http://<PC_IP>:8000`)
- **필수 참조**: `PRD-0-context.md`, `PRD-4-api.md`, `PRD-8-video-input-spec.md`

---

## ✅ 완료 조건 (Definition of Done)

- [ ] React Native 프로젝트 초기화 완료
- [ ] AR 가이드라인 오버레이가 카메라 프리뷰 위에 표시
- [ ] **카메라 화면이 가로 방향(landscape) 고정** — PRD-8 의 `PORTRAIT_NOT_SUPPORTED` 사전 차단
- [ ] **촬영 직전 가이드 모달** 표시 (`captureGuide` i18n, PRD-8 §7)
- [ ] 촬영 후 720p 다운스케일 + 압축 자동 처리 **(fps 는 원본 유지, `-r` 옵션 없음)**
- [ ] WiFi LAN으로 서버 업로드 성공
- [ ] 업로드 진행 상태바 표시
- [ ] **업로드 응답 HTTP 400 + `error_code` 수신 시 한국어 에러 화면** (PRD-4 §7a 카탈로그)
- [ ] 분석 진행 상태 폴링 (3초 간격)
- [ ] 트레이너 모드 토글 동작 (Context API)
- [ ] 회원 선택 UI (트레이너 모드 ON 시)
- [ ] 모든 UI 텍스트 한국어
- [ ] 실기기에서 end-to-end 테스트 통과 (정상 영상 + 거부 영상 양쪽)

---

## 📋 작업 항목

### 1. 프로젝트 초기화

```bash
# React Native 신규 프로젝트 (TypeScript)
npx react-native init treadform_app --template react-native-template-typescript
cd treadform_app

# 핵심 의존성 설치
npm install react-native-vision-camera        # 카메라
npm install react-native-svg                  # AR 가이드라인 SVG
npm install ffmpeg-kit-react-native           # 720p 다운스케일
npm install @react-navigation/native @react-navigation/native-stack
npm install react-native-screens react-native-safe-area-context
npm install axios                             # API 호출
npm install @react-native-async-storage/async-storage  # 모드 상태 저장
npm install react-i18next i18next             # 한국어 i18n
```

### 2. 앱 프로젝트 구조

```
app/
├── App.tsx
├── package.json
├── src/
│   ├── screens/
│   │   ├── HomeScreen.tsx               # 메인 (촬영 시작 버튼)
│   │   ├── CameraScreen.tsx             # AR 가이드라인 카메라
│   │   ├── UploadScreen.tsx             # 업로드 진행
│   │   ├── ProcessingScreen.tsx         # 분석 폴링 대기 화면
│   │   └── MemberSelectScreen.tsx       # 트레이너 모드 회원 선택
│   │
│   ├── components/
│   │   ├── ARGuideOverlay.tsx           # 반투명 가이드라인 SVG
│   │   ├── RecordButton.tsx             # 촬영 버튼
│   │   ├── ModeToggle.tsx               # 트레이너 모드 토글
│   │   └── UploadProgressBar.tsx
│   │
│   ├── services/
│   │   ├── api.ts                       # axios 인스턴스 + 엔드포인트
│   │   ├── videoProcessor.ts            # ffmpeg로 720p 변환
│   │   └── storage.ts                   # AsyncStorage 래퍼
│   │
│   ├── context/
│   │   └── ModeContext.tsx              # 트레이너/일반 모드 전역 상태
│   │
│   ├── constants/
│   │   ├── colors.ts                    # COLOR_SAFE, WARNING, DANGER
│   │   └── api.ts                       # BASE_URL
│   │
│   └── i18n/
│       ├── index.ts
│       └── ko.json                      # 한국어 문자열
```

### 3. `src/constants/colors.ts`

```typescript
export const COLORS = {
  SAFE: '#22C55E',
  WARNING: '#EAB308',
  DANGER: '#EF4444',
  PRIMARY: '#1F4E79',
  BACKGROUND: '#FFFFFF',
  TEXT: '#1F2937',
  TEXT_SECONDARY: '#6B7280',
} as const;
```

### 4. `src/constants/api.ts`

```typescript
// 환경별 BASE_URL 분기 (개발 단계에서는 PC의 로컬 IP 직접 입력)
// 실기기 테스트 시: react-native run-android/ios 후 PC IP 수동 입력 필요
export const BASE_URL = 'http://192.168.1.100:8000';  // ⚠️ 본인 PC IP로 변경

export const ENDPOINTS = {
  UPLOAD: '/api/upload',
  ANALYSIS: (id: string) => `/api/analysis/${id}`,
  MEMBERS: '/api/members',
  MEMBER_HISTORY: (id: string) => `/api/members/${id}/history`,
} as const;
```

### 5. `src/services/api.ts`

```typescript
import axios from 'axios';
import { BASE_URL, ENDPOINTS } from '../constants/api';

const api = axios.create({
  baseURL: BASE_URL,
  timeout: 30000,
});

export interface UploadResponse {
  analysis_id: string;
  status: 'processing';
  estimated_seconds: number;
}

export async function uploadVideo(
  videoUri: string,
  memberId?: string,
  onProgress?: (percent: number) => void
): Promise<UploadResponse> {
  const formData = new FormData();
  formData.append('video', {
    uri: videoUri,
    type: 'video/mp4',
    name: 'run.mp4',
  } as any);
  if (memberId) formData.append('member_id', memberId);

  const response = await api.post(ENDPOINTS.UPLOAD, formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    onUploadProgress: (e) => {
      if (e.total) onProgress?.(Math.round((e.loaded / e.total) * 100));
    },
  });

  return response.data;
}

export async function getAnalysisResult(analysisId: string) {
  const response = await api.get(ENDPOINTS.ANALYSIS(analysisId));
  return response.data;
}

export async function createMember(name: string, trainerId: string) {
  const response = await api.post(ENDPOINTS.MEMBERS, { name, trainer_id: trainerId });
  return response.data;
}

export async function listMembers(trainerId: string) {
  const response = await api.get(`${ENDPOINTS.MEMBERS}?trainer_id=${trainerId}`);
  return response.data;
}
```

### 6. `src/services/videoProcessor.ts` (720p 다운스케일)

```typescript
import { FFmpegKit } from 'ffmpeg-kit-react-native';
import RNFS from 'react-native-fs';

/**
 * 1080p 영상을 720p로 다운스케일 + 비트레이트 조정.
 * 원본: 150~300MB → 출력: 50~100MB 수준.
 *
 * ⚠️ PRD-8 함정 #7: fps 보존이 매우 중요.
 *   - `-r` 옵션을 명시하지 *말 것* — ffmpeg 가 입력 fps 를 그대로 유지함.
 *   - `-r 30` 을 강제로 넣으면 원본 60fps 영상이 30fps 로 강등되어
 *     서버의 HIGH_CADENCE_LOW_FPS 경고가 의미를 잃음.
 *   - 60fps 빠른 페이스 사용자가 이득을 보려면 원본 fps 가 유지되어야.
 */
export async function downscaleTo720p(inputUri: string): Promise<string> {
  const outputUri = `${RNFS.CachesDirectoryPath}/downscaled_${Date.now()}.mp4`;

  // -vf scale=-2:720 : 가로 자동, 세로 720p
  // -b:v 2500k       : 비트레이트 2.5Mbps
  // -an              : 음성 제거
  // (-r 옵션 부재)   : 원본 fps 보존 (PRD-8 #7)
  const command = `-i "${inputUri}" -vf scale=-2:720 -b:v 2500k -an -y "${outputUri}"`;

  const session = await FFmpegKit.execute(command);
  const returnCode = await session.getReturnCode();

  if (returnCode.isValueSuccess()) {
    return outputUri;
  }
  throw new Error('영상 변환 실패');
}
```

### 7. `src/context/ModeContext.tsx`

```typescript
import React, { createContext, useContext, useState, useEffect } from 'react';
import AsyncStorage from '@react-native-async-storage/async-storage';

type Mode = 'general' | 'trainer';

interface ModeContextType {
  mode: Mode;
  setMode: (m: Mode) => void;
  selectedMemberId: string | null;
  setSelectedMemberId: (id: string | null) => void;
  trainerId: string | null;
}

const ModeContext = createContext<ModeContextType | undefined>(undefined);

export const ModeProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [mode, setModeState] = useState<Mode>('general');
  const [selectedMemberId, setSelectedMemberId] = useState<string | null>(null);
  const [trainerId, setTrainerId] = useState<string | null>(null);

  // 앱 시작 시 저장된 모드 복원
  useEffect(() => {
    AsyncStorage.getItem('mode').then((saved) => {
      if (saved === 'trainer' || saved === 'general') setModeState(saved);
    });
    AsyncStorage.getItem('trainer_id').then(setTrainerId);
  }, []);

  const setMode = (m: Mode) => {
    setModeState(m);
    AsyncStorage.setItem('mode', m);
  };

  return (
    <ModeContext.Provider value={{ mode, setMode, selectedMemberId, setSelectedMemberId, trainerId }}>
      {children}
    </ModeContext.Provider>
  );
};

export const useMode = () => {
  const ctx = useContext(ModeContext);
  if (!ctx) throw new Error('useMode must be inside ModeProvider');
  return ctx;
};
```

### 8. `src/components/ARGuideOverlay.tsx` (반투명 가이드라인)

```typescript
import React from 'react';
import { Dimensions } from 'react-native';
import Svg, { Line, Rect, Text } from 'react-native-svg';

const { width: W, height: H } = Dimensions.get('window');

export const ARGuideOverlay: React.FC = () => {
  // 트레드밀 벨트 선 (화면 하단 1/3 지점)
  const beltY = H * 0.7;
  // 골반 가이드 박스 (화면 중앙)
  const hipBoxX = W * 0.4;
  const hipBoxY = H * 0.4;

  return (
    <Svg style={{ position: 'absolute', top: 0, left: 0 }} width={W} height={H}>
      {/* 트레드밀 벨트 선 */}
      <Line x1={0} y1={beltY} x2={W} y2={beltY}
            stroke="rgba(34, 197, 94, 0.7)" strokeWidth={3} strokeDasharray="10,5" />
      <Text x={20} y={beltY - 10} fill="rgba(34, 197, 94, 0.9)" fontSize={14}>
        트레드밀 벨트에 맞춰주세요
      </Text>

      {/* 골반 위치 가이드 박스 */}
      <Rect x={hipBoxX} y={hipBoxY} width={W * 0.2} height={H * 0.1}
            stroke="rgba(34, 197, 94, 0.7)" strokeWidth={2} fill="none" strokeDasharray="5,5" />
      <Text x={hipBoxX} y={hipBoxY - 10} fill="rgba(34, 197, 94, 0.9)" fontSize={12}>
        골반 위치
      </Text>
    </Svg>
  );
};
```

### 9. `src/screens/CameraScreen.tsx`

```typescript
import React, { useRef, useState } from 'react';
import { View, TouchableOpacity, Text, StyleSheet } from 'react-native';
import { Camera, useCameraDevice } from 'react-native-vision-camera';
import { ARGuideOverlay } from '../components/ARGuideOverlay';
import { downscaleTo720p } from '../services/videoProcessor';
import { useNavigation } from '@react-navigation/native';

export const CameraScreen: React.FC = () => {
  const device = useCameraDevice('back');
  const camera = useRef<Camera>(null);
  const [isRecording, setIsRecording] = useState(false);
  const navigation = useNavigation();

  const handleRecord = async () => {
    if (!camera.current) return;

    if (isRecording) {
      // 녹화 중지
      await camera.current.stopRecording();
    } else {
      // 녹화 시작
      setIsRecording(true);
      camera.current.startRecording({
        onRecordingFinished: async (video) => {
          setIsRecording(false);
          // 720p 다운스케일
          const downscaled = await downscaleTo720p(video.path);
          // UploadScreen으로 이동
          navigation.navigate('Upload' as never, { videoUri: downscaled } as never);
        },
        onRecordingError: (error) => {
          console.error('녹화 오류:', error);
          setIsRecording(false);
        },
      });
    }
  };

  if (!device) return <Text>카메라를 사용할 수 없습니다</Text>;

  return (
    <View style={styles.container}>
      <Camera
        ref={camera}
        style={StyleSheet.absoluteFill}
        device={device}
        isActive={true}
        video={true}
      />
      <ARGuideOverlay />
      <View style={styles.bottomBar}>
        <TouchableOpacity
          style={[styles.recordButton, isRecording && styles.recording]}
          onPress={handleRecord}
        >
          <Text style={styles.recordButtonText}>
            {isRecording ? '녹화 중지' : '녹화 시작'}
          </Text>
        </TouchableOpacity>
      </View>
    </View>
  );
};

const styles = StyleSheet.create({
  container: { flex: 1 },
  bottomBar: { position: 'absolute', bottom: 50, left: 0, right: 0, alignItems: 'center' },
  recordButton: {
    backgroundColor: '#22C55E', paddingHorizontal: 30, paddingVertical: 15, borderRadius: 30,
  },
  recording: { backgroundColor: '#EF4444' },
  recordButtonText: { color: 'white', fontSize: 18, fontWeight: 'bold' },
});
```

### 10. `src/screens/UploadScreen.tsx`

```typescript
import React, { useEffect, useState } from 'react';
import { View, Text, StyleSheet, ProgressBarAndroid } from 'react-native';
import { uploadVideo } from '../services/api';
import { useMode } from '../context/ModeContext';
import { useNavigation, useRoute } from '@react-navigation/native';

export const UploadScreen: React.FC = () => {
  const route = useRoute();
  const navigation = useNavigation();
  const { videoUri } = route.params as { videoUri: string };
  const { selectedMemberId } = useMode();
  const [progress, setProgress] = useState(0);
  const [status, setStatus] = useState('업로드 준비 중...');

  useEffect(() => {
    (async () => {
      try {
        setStatus('영상 업로드 중...');
        const result = await uploadVideo(
          videoUri,
          selectedMemberId || undefined,
          setProgress
        );
        setStatus('업로드 완료. 분석 시작...');
        navigation.replace('Processing' as never, { analysisId: result.analysis_id } as never);
      } catch (error) {
        setStatus(`오류 발생: ${error}`);
      }
    })();
  }, [videoUri]);

  return (
    <View style={styles.container}>
      <Text style={styles.title}>러닝 영상 업로드</Text>
      <Text style={styles.status}>{status}</Text>
      <View style={styles.progressContainer}>
        <Text style={styles.percent}>{progress}%</Text>
        {/* iOS는 ProgressViewIOS, Android는 ProgressBarAndroid; 통합 라이브러리 권장 */}
      </View>
    </View>
  );
};

const styles = StyleSheet.create({
  container: { flex: 1, justifyContent: 'center', alignItems: 'center', padding: 20 },
  title: { fontSize: 24, fontWeight: 'bold', marginBottom: 30 },
  status: { fontSize: 16, marginBottom: 20, color: '#6B7280' },
  progressContainer: { width: '100%', alignItems: 'center' },
  percent: { fontSize: 32, fontWeight: 'bold', color: '#22C55E' },
});
```

### 11. `src/screens/ProcessingScreen.tsx` (폴링 로직)

```typescript
import React, { useEffect, useState } from 'react';
import { View, Text, ActivityIndicator } from 'react-native';
import { getAnalysisResult } from '../services/api';
import { useNavigation, useRoute } from '@react-navigation/native';

export const ProcessingScreen: React.FC = () => {
  const route = useRoute();
  const navigation = useNavigation();
  const { analysisId } = route.params as { analysisId: string };
  const [status, setStatus] = useState('분석 중...');

  useEffect(() => {
    const pollInterval = setInterval(async () => {
      try {
        const result = await getAnalysisResult(analysisId);
        if (result.status === 'completed') {
          clearInterval(pollInterval);
          // ResultScreen으로 이동 (Step 6에서 구현)
          navigation.replace('Result' as never, { result } as never);
        } else if (result.status === 'failed') {
          clearInterval(pollInterval);
          setStatus(`분석 실패: ${result.error}`);
        }
      } catch (error) {
        console.error(error);
      }
    }, 3000); // 3초마다 폴링

    return () => clearInterval(pollInterval);
  }, [analysisId]);

  return (
    <View style={{ flex: 1, justifyContent: 'center', alignItems: 'center' }}>
      <ActivityIndicator size="large" color="#22C55E" />
      <Text style={{ marginTop: 20, fontSize: 18 }}>{status}</Text>
      <Text style={{ marginTop: 10, color: '#6B7280' }}>잠시만 기다려주세요 (약 30초)</Text>
    </View>
  );
};
```

### 12. `src/components/ModeToggle.tsx` + `MemberSelectScreen.tsx`

```typescript
// ModeToggle: 홈 화면 상단에 표시
// 트레이너 모드 ON 시 회원 선택 화면으로 이동
```

### 13. `src/i18n/ko.json`

```json
{
  "home": {
    "title": "TreadForm",
    "subtitle": "트레드밀 러닝 자세 분석",
    "startRecord": "촬영 시작",
    "trainerMode": "트레이너 모드"
  },
  "camera": {
    "guide": "트레드밀 벨트에 맞춰주세요",
    "record": "녹화 시작",
    "stop": "녹화 중지"
  },
  "captureGuide": {
    "title": "정확한 분석을 위한 촬영 가이드",
    "checklist": [
      "카메라를 삼각대 또는 거치대로 고정",
      "트레드밀 옆에서 골반 높이로 촬영",
      "전신이 화면의 60~80%를 차지",
      "단색 배경, 밝은 조명",
      "몸에 붙는 옷 (헐렁한 옷 X)",
      "5~30초 분량 (10보 이상)",
      "편안하게 5분 이상 유지 가능한 페이스로 (5:30~6:30/km 권장)"
    ],
    "settingsTitle": "권장 촬영 설정",
    "settings": [
      "방향: 가로 (세로 영상은 거부됩니다)",
      "해상도: 1280×720 이상 (1080p 권장)",
      "프레임률: 30fps 이상 (빠른 러너는 60fps 필수)",
      "길이: 5~60초",
      "페이스 4:30/km 이하로 분석하려면 60fps 필수"
    ],
    "paceGuide": {
      "title": "권장 페이스",
      "recommendation": "편안하게 5분 이상 유지 가능한 페이스 (보통 5:30~6:30/km)",
      "warningFast": "4:30/km 이하 빠른 페이스는 60fps 촬영을 권장합니다.",
      "warningSlow": "조깅(7:00/km 이상)은 러닝 자세가 명확히 드러나지 않아 분석 정확도가 떨어질 수 있습니다."
    },
    "confirm": "이해했습니다, 촬영 시작"
  },
  "upload": {
    "title": "러닝 영상 업로드",
    "uploading": "영상 업로드 중...",
    "completed": "업로드 완료"
  },
  "errorCodes": {
    "INVALID_EXTENSION": "MP4 또는 MOV 파일만 업로드할 수 있습니다.",
    "CANNOT_OPEN_VIDEO": "영상 파일을 열 수 없습니다. 다시 촬영해주세요.",
    "PORTRAIT_NOT_SUPPORTED": "세로 영상은 분석할 수 없습니다. 휴대폰을 가로로 돌려 다시 촬영해주세요.",
    "RESOLUTION_TOO_LOW": "해상도가 너무 낮습니다. 1280×720 이상으로 촬영해주세요.",
    "FPS_TOO_LOW": "프레임률이 너무 낮습니다. 카메라 설정에서 30fps 이상으로 변경해주세요.",
    "DURATION_TOO_SHORT": "영상이 너무 짧습니다. 5초 이상 촬영해주세요.",
    "DURATION_TOO_LONG": "영상이 너무 깁니다. 60초 이내로 촬영해주세요.",
    "_default": "영상 검증에 실패했습니다."
  },
  "processing": {
    "analyzing": "분석 중...",
    "pleaseWait": "잠시만 기다려주세요 (약 30초)"
  }
}
```

> 📌 클라이언트는 서버 응답의 `error_code` 로 `errorCodes.<CODE>` 키를 매핑한다. 매핑 실패 시 서버가 보낸 `message_ko` 를 그대로 표시하고 `_default` 를 폴백으로 사용.

### 13a. CameraScreen 진입 시 가이드 모달 + 가로 방향 강제

```typescript
// src/screens/CameraScreen.tsx (보강분)
import Orientation from 'react-native-orientation-locker';
import { CaptureGuideModal } from '../components/CaptureGuideModal';

export const CameraScreen: React.FC = () => {
  const [guideShown, setGuideShown] = useState(true);

  useEffect(() => {
    Orientation.lockToLandscape();    // PRD-8: 가로 강제
    return () => Orientation.unlockAllOrientations();
  }, []);

  if (guideShown) {
    return <CaptureGuideModal onConfirm={() => setGuideShown(false)} />;
  }
  // ... 카메라 UI ...
};
```

`CaptureGuideModal` 은 `i18n('captureGuide')` 의 체크리스트 + 설정을 표시하고 "이해했습니다" 버튼으로 닫는 단순 모달. PRD-6 의 결과 화면과 동일한 색상 토큰 사용.

### 13b. UploadScreen 에서 HTTP 400 + error_code 처리

```typescript
// src/screens/UploadScreen.tsx (보강분)
try {
  const result = await uploadVideo(videoUri, selectedMemberId);
  navigation.replace('Processing', { analysisId: result.analysis_id });
} catch (error: any) {
  // axios 는 4xx 를 reject 함.
  const detail = error?.response?.data?.detail;
  if (detail?.error_code) {
    const i18nKey = `errorCodes.${detail.error_code}`;
    const message = t(i18nKey, { defaultValue: detail.message_ko ?? t('errorCodes._default') });
    navigation.replace('Camera', { errorMessage: message });  // 재촬영 유도
  } else {
    navigation.replace('Camera', { errorMessage: t('errorCodes._default') });
  }
}
```

---

## 🧪 검증 방법

### 1단계: 시뮬레이터/에뮬레이터 실행
```bash
cd app
npx react-native run-ios       # 또는 run-android
```

### 2단계: 실기기 빌드 (필수)
- 카메라/녹화는 실기기에서만 정상 동작
- iOS: Xcode에서 본인 Apple ID로 서명 후 폰에 빌드
- Android: USB 디버깅 활성화 후 `npx react-native run-android`

### 3단계: end-to-end 시나리오
1. PC에서 `uvicorn main:app --host 0.0.0.0 --port 8000` 실행 중
2. 폰과 PC를 같은 WiFi에 연결
3. `app/src/constants/api.ts`의 `BASE_URL`을 PC IP로 설정
4. 앱에서 촬영 → 720p 변환 → 업로드 진행률 표시 → 분석 폴링 → 완료 확인

### 4단계: 트레이너 모드 검증
1. 트레이너 모드 토글 ON
2. 회원 등록 (`POST /api/members`)
3. 회원 선택 후 촬영
4. 업로드 시 `member_id` 자동 전달 확인
5. `GET /api/members/{id}/history`로 누적 데이터 확인

---

## 💬 추천 Vibe Coding 명령

```
1. "PRD-5-app-capture.md를 보고 React Native 프로젝트 초기 세팅 + 의존성 설치 명령어 정리. 각 패키지의 iOS/Android 추가 설정 안내 포함."

2. "src/services/api.ts와 src/constants/api.ts 구현. axios 인스턴스, FormData 영상 업로드, 진행률 콜백 포함."

3. "src/services/videoProcessor.ts에 ffmpeg-kit으로 720p 다운스케일 함수 구현. 비트레이트 2.5Mbps, 음성 제거."

4. "src/context/ModeContext.tsx 구현. AsyncStorage로 모드 영속화."

5. "src/components/ARGuideOverlay.tsx 구현. SVG로 트레드밀 벨트 선 + 골반 박스 가이드."

6. "src/screens/CameraScreen.tsx 구현. react-native-vision-camera로 녹화 + AR 오버레이 + 자동 720p 변환."

7. "src/screens/UploadScreen.tsx와 ProcessingScreen.tsx 구현. 업로드 진행률 표시 + 3초 폴링."

8. "i18n/ko.json에 모든 UI 문자열 한국어로 정의. App.tsx에 i18next 초기화."

9. "App.tsx 작성. NavigationContainer + ModeProvider + Stack Navigator로 모든 화면 연결."
```

---

## 📤 산출물

### 생성될 파일
```
app/
├── App.tsx
├── package.json
├── src/
│   ├── screens/ (Home, Camera, Upload, Processing, MemberSelect)
│   ├── components/ (ARGuideOverlay, RecordButton, ModeToggle, UploadProgressBar)
│   ├── services/ (api.ts, videoProcessor.ts, storage.ts)
│   ├── context/ModeContext.tsx
│   ├── constants/ (colors.ts, api.ts)
│   └── i18n/ (index.ts, ko.json)
└── android/ios/ (네이티브 설정)
```

### 다음 단계로 넘길 인터페이스

**Step 6(앱 결과 화면)이 받을 데이터**:

```typescript
// ProcessingScreen에서 polling 후 받은 결과를 ResultScreen으로 전달
navigation.replace('Result', { result: AnalysisAPIResponse });

interface AnalysisAPIResponse {
  analysis_id: string;
  status: 'completed';
  rendered_video_url: string;   // http://<PC>:8000/storage/renders/{id}.mp4
  csv_url: string;
  summary: object;
  metrics: object;
  asymmetry: object;
  danger_timestamps: Array<{ time_sec: number; type: string; color: string }>;
  coach_message_ko: string;
}
```

---

## ⚠️ 흔한 함정

1. **카메라 권한**
   - iOS: `Info.plist`에 `NSCameraUsageDescription`, `NSMicrophoneUsageDescription`
   - Android: `AndroidManifest.xml`에 `CAMERA`, `RECORD_AUDIO` 권한

2. **ffmpeg-kit-react-native 설정 복잡**
   - iOS: `Podfile`에 `pod 'ffmpeg-kit-react-native', :subspecs => ['full']`
   - Android: `android/build.gradle`에 패키지 추가
   - 빌드 시간 길어짐 (15~30분)

3. **로컬 IP가 자주 바뀜**
   - WiFi 재연결 시 PC IP가 변경될 수 있음
   - 개발 중에는 PC에 고정 IP 설정 권장

4. **iOS 시뮬레이터의 한계**
   - 시뮬레이터는 카메라 미지원 → 실기기 필수
   - WiFi LAN 통신도 실기기에서만 검증 가능

5. **Android Cleartext HTTP 차단**
   - Android 9+ 기본적으로 HTTP 차단
   - `android/app/src/main/AndroidManifest.xml`에 `usesCleartextTraffic="true"` 추가
   - 또는 `network_security_config.xml`에서 개발용 IP 허용

6. **업로드 시 메모리 이슈**
   - 큰 영상을 한 번에 메모리에 올리면 OOM 발생
   - axios의 스트리밍 업로드 고려 또는 영상을 chunk로 분할

7. **iOS 백그라운드 처리 제한**
   - 앱이 백그라운드 가면 ffmpeg 변환 중단됨
   - 변환 중에는 화면 유지 (Activity Indicator 표시)

8. **ffmpeg `-r` 옵션으로 fps 강등** _(2026-05-15, PRD-8)_
   - 다운스케일 명령에 `-r 30` 을 넣으면 원본 60fps 가 30fps 로 떨어짐
   - 결과적으로 빠른 페이스 사용자가 `HIGH_CADENCE_LOW_FPS` 경고를 피할 방법 없음
   - 해결책: `-r` 옵션 *생략* → ffmpeg 가 입력 fps 그대로 유지

9. **세로 영상이 서버에서 거부됨** _(2026-05-15, PRD-8)_
   - `running_video_se.mp4` 실측에서 1080×1920 portrait 가 `PORTRAIT_NOT_SUPPORTED` 거부
   - CameraScreen 진입 시 `react-native-orientation-locker` 로 가로 강제하고,
     촬영 직전 가이드 모달에 "휴대폰을 가로로" 명시할 것
   - 사용자가 시스템 카메라로 따로 찍어 갤러리 업로드하는 경로가 있다면
     클라이언트에서도 width < height 사전 차단 권장

10. **`error_code` i18n 미매핑** _(2026-05-15)_
    - 서버가 새 `error_code` 추가했는데 앱이 매핑 추가를 잊으면 영문 코드가 그대로 노출
    - `errorCodes._default` 폴백 + 서버 `message_ko` 그대로 표시로 안전망 구성

11. **권장 페이스 안내 누락** _(2026-05-15)_
    - PRD-8 `HIGH_CADENCE_LOW_FPS` 경고는 "이러면 안 됨" 의 negative guard 일 뿐.
      사용자가 **어떤 페이스로 찍어야 신뢰도 high 가 나오는지** positive guidance 가 없으면
      매번 medium 등급으로 떨어진 후에야 학습하게 됨.
    - 권장 sweet spot: **5:30~6:30/km** (30fps 환경 기준).
      자세한 페이스 × fps 매트릭스는 PRD-8 §"권장 페이스" 참조.
    - `captureGuide.paceGuide` 항목으로 i18n 에 박혀있으므로 CameraScreen 진입 모달에서
      반드시 노출. 빠른 페이스 사용자에게는 60fps 촬영 안내를 함께 표시.
