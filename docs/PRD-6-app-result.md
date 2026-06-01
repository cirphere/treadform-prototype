# PRD-6: 앱 - 결과 표시 & 누적 대시보드

> 📍 항상 함께 참조: **[PRD-0-context.md](./PRD-0-context.md)**
> 📍 이전 단계 산출물: **[PRD-5-app-capture.md](./PRD-5-app-capture.md)**
> 📍 교차 참조: **[PRD-8-video-input-spec.md](./PRD-8-video-input-spec.md)** (신뢰도 배지, 경고 리스트)

---

## 🎯 이 단계의 목표

서버에서 받은 분석 결과를 사용자에게 **직관적으로** 보여주는 화면을 완성한다. **Danger 마커 + 0.5x 슬로우 모션 플레이어**, **🔴🟡🟢 색상 뱃지**, **비포/애프터 누적 대시보드 그래프**, **PRD-8 신뢰도/경고 표시**를 구현하여 end-to-end 사용자 플로우를 마무리한다.

---

## 📥 입력 (의존성)

- **이전 단계 산출물**:
    - Processing 화면에서 폴링 완료된 `AnalysisAPIResponse` (PRD-8 의 `confidence`/`warnings` 포함)
    - 서버의 `/storage/renders/{id}.mp4` 영상 URL
    - 서버의 `/api/members/{id}/history` 누적 데이터
- **필수 참조**: `PRD-0-context.md`, `PRD-5-app-capture.md`, `PRD-8-video-input-spec.md`

---

## ✅ 완료 조건 (Definition of Done)

- [ ] 분석 결과 화면에서 렌더링 영상 인앱 재생
- [ ] 타임라인에 Danger 빨간 마커 표시
- [ ] Danger 구간 진입 시 자동 0.5배속 재생
- [ ] 3대 지표 + 비대칭 🔴🟡🟢 뱃지로 시각화
- [ ] 한국어 코칭 메시지 카드 형태로 표시
- [ ] **결과 화면 상단에 신뢰도 배지** (`high`/`medium`/`low`, PRD-8)
- [ ] **경고 리스트 카드** (`warnings[].message_ko`, 빈 배열일 땐 미표시)
- [ ] **신뢰도 `low` 시 결과 화면 톤다운** (메트릭/코칭 영역 30% 투명도 + "참고용" 워터마크)
- [ ] 회원별 누적 대시보드 그래프 (트레이너 모드)
- [ ] CSV 다운로드 / 결과 공유 기능
- [ ] 모든 UI 한국어
- [ ] 실기기에서 슬로우 모션 자동 전환 동작 확인

---

## 📋 작업 항목

### 1. 추가 의존성 설치

```bash
npm install react-native-video           # 영상 재생
npm install react-native-chart-kit       # 그래프
npm install react-native-svg             # 차트 의존성 (이미 설치됨)
npm install @react-native-community/slider  # 타임라인 슬라이더
npm install react-native-share           # 결과 공유
```

### 2. 추가 디렉토리 구조

```
src/
├── screens/
│   ├── ResultScreen.tsx              # 분석 결과 메인
│   └── DashboardScreen.tsx           # 누적 대시보드 (트레이너 모드)
│
├── components/
│   ├── VideoPlayerWithMarkers.tsx    # Danger 마커 + 슬로우 모션
│   ├── MetricBadge.tsx               # 🔴🟡🟢 색상 뱃지
│   ├── CoachMessageCard.tsx          # 한국어 코칭 메시지
│   ├── MetricsSummary.tsx            # 4대 지표 요약
│   ├── ProgressChart.tsx             # 비포/애프터 그래프
│   ├── ConfidenceBadge.tsx           # PRD-8 신뢰도 배지
│   └── WarningList.tsx               # PRD-8 경고 리스트 카드
│
└── hooks/
    └── useSlowMotionAtDanger.ts      # Danger 구간 자동 슬로우 모션
```

### 3. `src/hooks/useSlowMotionAtDanger.ts`

```typescript
import { useState, useCallback } from 'react';

interface DangerTimestamp {
  time_sec: number;
  type: string;
  color: string;
}

interface UseSlowMotionParams {
  dangerTimestamps: DangerTimestamp[];
  windowSec: number;  // Danger 시점 ±이 값만큼 슬로우
}

/**
 * 현재 재생 시점이 Danger 구간(±windowSec)에 있으면 0.5x,
 * 아니면 1.0x 자동 전환.
 */
export function useSlowMotionAtDanger({
  dangerTimestamps,
  windowSec = 0.5,
}: UseSlowMotionParams) {
  const [rate, setRate] = useState(1.0);

  const handleProgress = useCallback((currentSec: number) => {
    const isInDanger = dangerTimestamps.some(
      (d) => Math.abs(d.time_sec - currentSec) < windowSec
    );
    setRate(isInDanger ? 0.5 : 1.0);
  }, [dangerTimestamps, windowSec]);

  return { rate, handleProgress };
}
```

### 4. `src/components/VideoPlayerWithMarkers.tsx`

```typescript
import React, { useRef, useState } from 'react';
import { View, StyleSheet, Dimensions, TouchableOpacity, Text } from 'react-native';
import Video, { VideoRef } from 'react-native-video';
import Svg, { Circle, Line } from 'react-native-svg';
import { useSlowMotionAtDanger } from '../hooks/useSlowMotionAtDanger';
import { COLORS } from '../constants/colors';

interface DangerTimestamp {
  time_sec: number;
  type: string;
  color: string;
}

interface Props {
  videoUrl: string;
  dangerTimestamps: DangerTimestamp[];
}

const { width: SCREEN_W } = Dimensions.get('window');
const TIMELINE_HEIGHT = 40;

export const VideoPlayerWithMarkers: React.FC<Props> = ({ videoUrl, dangerTimestamps }) => {
  const videoRef = useRef<VideoRef>(null);
  const [duration, setDuration] = useState(0);
  const [currentTime, setCurrentTime] = useState(0);
  const [paused, setPaused] = useState(false);

  const { rate, handleProgress } = useSlowMotionAtDanger({
    dangerTimestamps,
    windowSec: 0.5,
  });

  return (
    <View style={styles.container}>
      <Video
        ref={videoRef}
        source={{ uri: videoUrl }}
        style={styles.video}
        rate={rate}
        paused={paused}
        onLoad={(meta) => setDuration(meta.duration)}
        onProgress={(p) => {
          setCurrentTime(p.currentTime);
          handleProgress(p.currentTime);
        }}
        resizeMode="contain"
      />

      {/* 슬로우 모션 상태 표시 */}
      {rate < 1.0 && (
        <View style={styles.slowMoBadge}>
          <Text style={styles.slowMoText}>🐢 0.5x 슬로우 모션</Text>
        </View>
      )}

      {/* Danger 마커 타임라인 */}
      <View style={styles.timeline}>
        <Svg width={SCREEN_W} height={TIMELINE_HEIGHT}>
          {/* 전체 라인 */}
          <Line
            x1={0}
            y1={TIMELINE_HEIGHT / 2}
            x2={SCREEN_W}
            y2={TIMELINE_HEIGHT / 2}
            stroke="#E5E7EB"
            strokeWidth={4}
          />
          {/* 현재 진행 라인 */}
          <Line
            x1={0}
            y1={TIMELINE_HEIGHT / 2}
            x2={(currentTime / duration) * SCREEN_W}
            y2={TIMELINE_HEIGHT / 2}
            stroke={COLORS.PRIMARY}
            strokeWidth={4}
          />
          {/* Danger 마커들 */}
          {dangerTimestamps.map((d, i) => (
            <Circle
              key={i}
              cx={(d.time_sec / duration) * SCREEN_W}
              cy={TIMELINE_HEIGHT / 2}
              r={6}
              fill={COLORS.DANGER}
            />
          ))}
        </Svg>
      </View>

      <TouchableOpacity style={styles.playButton} onPress={() => setPaused(!paused)}>
        <Text style={styles.playButtonText}>{paused ? '▶️ 재생' : '⏸ 일시정지'}</Text>
      </TouchableOpacity>
    </View>
  );
};

const styles = StyleSheet.create({
  container: { width: '100%' },
  video: { width: '100%', aspectRatio: 16 / 9, backgroundColor: 'black' },
  slowMoBadge: {
    position: 'absolute', top: 10, right: 10,
    backgroundColor: 'rgba(239, 68, 68, 0.9)',
    paddingHorizontal: 12, paddingVertical: 6, borderRadius: 16,
  },
  slowMoText: { color: 'white', fontWeight: 'bold' },
  timeline: { paddingVertical: 10 },
  playButton: { padding: 12, alignItems: 'center' },
  playButtonText: { fontSize: 16, fontWeight: 'bold', color: COLORS.PRIMARY },
});
```

### 5. `src/components/MetricBadge.tsx`

```typescript
import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
import { COLORS } from '../constants/colors';

type Status = 'safe' | 'warning' | 'danger';

interface Props {
  label: string;          // "무릎 굴곡"
  value: string;          // "152.3°"
  status: Status;
  detail?: string;        // "안전"
}

const STATUS_CONFIG = {
  safe: { color: COLORS.SAFE, icon: '🟢', text: '안전' },
  warning: { color: COLORS.WARNING, icon: '🟡', text: '경고' },
  danger: { color: COLORS.DANGER, icon: '🔴', text: '위험' },
} as const;

export const MetricBadge: React.FC<Props> = ({ label, value, status, detail }) => {
  const config = STATUS_CONFIG[status];

  return (
    <View style={[styles.container, { borderColor: config.color }]}>
      <Text style={styles.icon}>{config.icon}</Text>
      <View style={styles.content}>
        <Text style={styles.label}>{label}</Text>
        <Text style={[styles.value, { color: config.color }]}>{value}</Text>
        <Text style={styles.detail}>{detail ?? config.text}</Text>
      </View>
    </View>
  );
};

const styles = StyleSheet.create({
  container: {
    flexDirection: 'row',
    padding: 16,
    borderRadius: 12,
    borderWidth: 2,
    marginBottom: 12,
    backgroundColor: 'white',
  },
  icon: { fontSize: 32, marginRight: 12 },
  content: { flex: 1 },
  label: { fontSize: 14, color: '#6B7280' },
  value: { fontSize: 24, fontWeight: 'bold', marginTop: 2 },
  detail: { fontSize: 13, color: '#6B7280', marginTop: 2 },
});
```

### 6. `src/components/CoachMessageCard.tsx`

```typescript
import React from 'react';
import { View, Text, StyleSheet } from 'react-native';

interface Props {
  message: string;
}

export const CoachMessageCard: React.FC<Props> = ({ message }) => (
  <View style={styles.card}>
    <Text style={styles.header}>🎯 AI 코칭 피드백</Text>
    <Text style={styles.message}>{message}</Text>
  </View>
);

const styles = StyleSheet.create({
  card: {
    backgroundColor: '#F0F9FF',
    padding: 20,
    borderRadius: 12,
    borderLeftWidth: 4,
    borderLeftColor: '#2E75B6',
    marginVertical: 16,
  },
  header: { fontSize: 14, fontWeight: 'bold', color: '#1F4E79', marginBottom: 8 },
  message: { fontSize: 16, lineHeight: 24, color: '#1F2937' },
});
```

### 7. `src/components/MetricsSummary.tsx` (3대 지표 + 비대칭 통합)

```typescript
import React from 'react';
import { View } from 'react-native';
import { MetricBadge } from './MetricBadge';

interface Props {
  metrics: any;       // API 응답의 metrics 객체
  asymmetry: any;
}

type Status = 'safe' | 'warning' | 'danger';

function pickKneeStatus(knee: any): { status: Status; detail: string } {
  const counts = knee.status_counts;
  const total = Object.values(counts).reduce((s: number, n: any) => s + n, 0);
  const dangerRatio = ((counts.stiff || 0) + (counts.over_bent || 0)) / total;
  if (dangerRatio > 0.3) return { status: 'danger', detail: '경직 또는 과굴곡' };
  if ((counts.borderline || 0) / total > 0.3) return { status: 'warning', detail: '경계 구간 많음' };
  return { status: 'safe', detail: '정상 범위' };
}

function pickFootStrikeStatus(fs: any): { status: Status; detail: string } {
  const counts = fs.status_counts;
  const total = Object.values(counts).reduce((s: number, n: any) => s + n, 0);
  if ((counts.heel || 0) / total > 0.5) return { status: 'danger', detail: '뒤꿈치 착지 우세' };
  if ((counts.forefoot || 0) / total > 0.3) return { status: 'warning', detail: '앞꿈치 비율 높음' };
  return { status: 'safe', detail: '중족 착지 안정' };
}

// ... overstriding, vertical_oscillation, asymmetry 동일 패턴

export const MetricsSummary: React.FC<Props> = ({ metrics, asymmetry }) => {
  const knee = pickKneeStatus(metrics.knee_flexion);
  const foot = pickFootStrikeStatus(metrics.foot_strike);
  // ...

  return (
    <View>
      <MetricBadge
        label="무릎 굴곡 각도"
        value={`${metrics.knee_flexion.avg_angle.toFixed(1)}°`}
        status={knee.status}
        detail={knee.detail}
      />
      <MetricBadge
        label="발 착지 유형"
        value={`Heel ${metrics.foot_strike.status_counts.heel || 0}회`}
        status={foot.status}
        detail={foot.detail}
      />
      {/* ... */}
    </View>
  );
};
```

### 7a. `src/components/ConfidenceBadge.tsx` (PRD-8 신뢰도)

```typescript
import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
import { COLORS } from '../constants/colors';

type Confidence = 'high' | 'medium' | 'low';

const CONFIDENCE_CONFIG: Record<Confidence, { color: string; label: string; description: string }> = {
  high:   { color: COLORS.SAFE,    label: '높음', description: '입력 영상 품질이 우수하여 분석을 신뢰할 수 있습니다.' },
  medium: { color: COLORS.WARNING, label: '보통', description: '일부 조건이 권장 사양에 미치지 못합니다. 아래 경고를 확인해주세요.' },
  low:    { color: COLORS.DANGER,  label: '낮음', description: '여러 조건이 미흡합니다. 결과는 참고용으로만 사용하고 재촬영을 권장합니다.' },
};

export const ConfidenceBadge: React.FC<{ confidence: Confidence }> = ({ confidence }) => {
  const config = CONFIDENCE_CONFIG[confidence];
  return (
    <View style={[styles.container, { backgroundColor: config.color }]}>
      <Text style={styles.label}>분석 신뢰도: {config.label}</Text>
      <Text style={styles.description}>{config.description}</Text>
    </View>
  );
};

const styles = StyleSheet.create({
  container: { padding: 14, borderRadius: 12, marginHorizontal: 20, marginBottom: 12 },
  label: { color: 'white', fontSize: 16, fontWeight: 'bold' },
  description: { color: 'white', fontSize: 12, marginTop: 4, opacity: 0.95 },
});
```

### 7b. `src/components/WarningList.tsx` (PRD-8 경고 리스트)

```typescript
import React from 'react';
import { View, Text, StyleSheet } from 'react-native';

interface Warning { code: string; message_ko: string; }

export const WarningList: React.FC<{ warnings: Warning[] }> = ({ warnings }) => {
  if (warnings.length === 0) return null;
  return (
    <View style={styles.card}>
      <Text style={styles.header}>⚠️ 입력 영상 경고 ({warnings.length}건)</Text>
      {warnings.map((w) => (
        <View key={w.code} style={styles.row}>
          <Text style={styles.bullet}>•</Text>
          <Text style={styles.message}>{w.message_ko}</Text>
        </View>
      ))}
    </View>
  );
};

const styles = StyleSheet.create({
  card: {
    marginHorizontal: 20, marginBottom: 12,
    padding: 14, borderRadius: 12,
    backgroundColor: '#FEF3C7',          // 옅은 노랑
    borderLeftWidth: 4, borderLeftColor: '#EAB308',
  },
  header: { fontSize: 14, fontWeight: 'bold', marginBottom: 8, color: '#92400E' },
  row: { flexDirection: 'row', marginVertical: 3 },
  bullet: { width: 12, color: '#92400E' },
  message: { flex: 1, fontSize: 13, color: '#78350F', lineHeight: 18 },
});
```

### 8. `src/screens/ResultScreen.tsx`

```typescript
import React from 'react';
import { ScrollView, View, Text, StyleSheet, TouchableOpacity } from 'react-native';
import { useRoute, useNavigation } from '@react-navigation/native';
import Share from 'react-native-share';
import { VideoPlayerWithMarkers } from '../components/VideoPlayerWithMarkers';
import { MetricsSummary } from '../components/MetricsSummary';
import { CoachMessageCard } from '../components/CoachMessageCard';
import { ConfidenceBadge } from '../components/ConfidenceBadge';
import { WarningList } from '../components/WarningList';
import { BASE_URL } from '../constants/api';

export const ResultScreen: React.FC = () => {
  const route = useRoute();
  const navigation = useNavigation();
  const { result } = route.params as { result: any };

  const fullVideoUrl = `${BASE_URL}${result.rendered_video_url}`;
  const csvUrl = `${BASE_URL}${result.csv_url}`;

  // PRD-8: low confidence 시 결과 영역 톤다운.
  const isLowConfidence = result.confidence === 'low';
  const contentOpacity = isLowConfidence ? 0.3 : 1.0;

  const handleShare = async () => {
    await Share.open({
      title: '러닝 자세 분석 결과',
      message: result.coach_message_ko,
      url: csvUrl,
    });
  };

  return (
    <ScrollView style={styles.container}>
      <Text style={styles.header}>러닝 자세 분석 결과</Text>

      {/* PRD-8: 신뢰도 배지 + 경고 리스트는 톤다운 영역 밖에 둔다. */}
      <ConfidenceBadge confidence={result.confidence} />
      <WarningList warnings={result.warnings} />

      <View style={{ opacity: contentOpacity }}>
        {isLowConfidence && (
          <View style={styles.lowBanner}>
            <Text style={styles.lowBannerText}>참고용 — 재촬영 후 다시 분석해주세요</Text>
          </View>
        )}

        <VideoPlayerWithMarkers
          videoUrl={fullVideoUrl}
          dangerTimestamps={result.danger_timestamps}
        />

        <CoachMessageCard message={result.coach_message_ko} />

        <View style={styles.section}>
          <Text style={styles.sectionTitle}>분석 결과 요약</Text>
          <MetricsSummary metrics={result.metrics} asymmetry={result.asymmetry} />
        </View>
      </View>

      <View style={styles.buttonRow}>
        <TouchableOpacity style={styles.shareButton} onPress={handleShare}>
          <Text style={styles.buttonText}>📤 결과 공유</Text>
        </TouchableOpacity>
        <TouchableOpacity
          style={styles.homeButton}
          onPress={() => navigation.navigate('Home' as never)}
        >
          <Text style={styles.buttonText}>🏠 처음으로</Text>
        </TouchableOpacity>
      </View>
    </ScrollView>
  );
};

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#F9FAFB' },
  header: { fontSize: 22, fontWeight: 'bold', padding: 20, color: '#1F4E79' },
  section: { padding: 20 },
  sectionTitle: { fontSize: 18, fontWeight: 'bold', marginBottom: 12 },
  buttonRow: { flexDirection: 'row', padding: 20, gap: 10 },
  shareButton: { flex: 1, backgroundColor: '#2E75B6', padding: 14, borderRadius: 8, alignItems: 'center' },
  homeButton: { flex: 1, backgroundColor: '#6B7280', padding: 14, borderRadius: 8, alignItems: 'center' },
  buttonText: { color: 'white', fontWeight: 'bold' },
  lowBanner: {
    marginHorizontal: 20, marginBottom: 10,
    paddingVertical: 8, paddingHorizontal: 12,
    backgroundColor: '#EF4444', borderRadius: 6,
  },
  lowBannerText: { color: 'white', fontWeight: 'bold', textAlign: 'center' },
});
```

### 9. `src/components/ProgressChart.tsx` (비포/애프터 그래프)

```typescript
import React from 'react';
import { View, Text, StyleSheet, Dimensions } from 'react-native';
import { LineChart } from 'react-native-chart-kit';

interface Props {
  title: string;
  labels: string[];        // ["1주차", "2주차", ...]
  values: number[];        // [15, 10, 7, 3]
  unit: string;            // "회"
}

const { width: SCREEN_W } = Dimensions.get('window');

export const ProgressChart: React.FC<Props> = ({ title, labels, values, unit }) => (
  <View style={styles.container}>
    <Text style={styles.title}>{title}</Text>
    <LineChart
      data={{
        labels,
        datasets: [{ data: values }],
      }}
      width={SCREEN_W - 40}
      height={220}
      yAxisSuffix={unit}
      chartConfig={{
        backgroundColor: '#FFFFFF',
        backgroundGradientFrom: '#FFFFFF',
        backgroundGradientTo: '#FFFFFF',
        decimalPlaces: 1,
        color: (opacity = 1) => `rgba(46, 117, 182, ${opacity})`,
        labelColor: () => '#374151',
      }}
      bezier
      style={{ marginVertical: 8, borderRadius: 12 }}
    />
  </View>
);

const styles = StyleSheet.create({
  container: { marginBottom: 24 },
  title: { fontSize: 16, fontWeight: 'bold', marginBottom: 8 },
});
```

### 10. `src/screens/DashboardScreen.tsx` (트레이너 모드 전용)

```typescript
import React, { useEffect, useState } from 'react';
import { ScrollView, Text, View, StyleSheet } from 'react-native';
import { useMode } from '../context/ModeContext';
import { api } from '../services/api';
import { ProgressChart } from '../components/ProgressChart';

export const DashboardScreen: React.FC = () => {
  const { selectedMemberId } = useMode();
  const [history, setHistory] = useState<any[]>([]);

  useEffect(() => {
    if (!selectedMemberId) return;
    api.get(`/api/members/${selectedMemberId}/history`).then((res) => {
      setHistory(res.data.history);
    });
  }, [selectedMemberId]);

  if (history.length === 0) {
    return (
      <View style={styles.empty}>
        <Text>분석 이력이 없습니다.</Text>
      </View>
    );
  }

  // 데이터 변환
  const labels = history.map((_, i) => `${i + 1}회`);
  const heelStrikes = history.map((h) => h.metrics.foot_strike.status_counts.heel || 0);
  const kneeAvg = history.map((h) => h.metrics.knee_flexion.avg_angle);
  const vertOsc = history.map((h) => h.metrics.vertical_oscillation.avg_value);

  return (
    <ScrollView style={styles.container}>
      <Text style={styles.header}>비포/애프터 누적 분석</Text>

      <ProgressChart
        title="뒤꿈치 착지 발생 횟수"
        labels={labels}
        values={heelStrikes}
        unit="회"
      />
      <ProgressChart
        title="평균 무릎 굴곡 각도"
        labels={labels}
        values={kneeAvg}
        unit="°"
      />
      <ProgressChart
        title="수직 진폭"
        labels={labels}
        values={vertOsc}
        unit=""
      />

      <View style={styles.summary}>
        <Text style={styles.summaryTitle}>📈 PT 효과 요약</Text>
        <Text style={styles.summaryText}>
          {`첫 회 ${heelStrikes[0]}회 → 최근 ${heelStrikes.at(-1)}회로 뒤꿈치 착지가 감소했습니다.`}
        </Text>
      </View>
    </ScrollView>
  );
};

const styles = StyleSheet.create({
  container: { flex: 1, padding: 20 },
  empty: { flex: 1, justifyContent: 'center', alignItems: 'center' },
  header: { fontSize: 22, fontWeight: 'bold', marginBottom: 20, color: '#1F4E79' },
  summary: { backgroundColor: '#F0F9FF', padding: 20, borderRadius: 12, marginTop: 16 },
  summaryTitle: { fontSize: 16, fontWeight: 'bold', marginBottom: 8 },
  summaryText: { fontSize: 15, lineHeight: 22 },
});
```

### 11. `i18n/ko.json` 업데이트

```json
{
  "result": {
    "title": "러닝 자세 분석 결과",
    "kneeFlexion": "무릎 굴곡 각도",
    "footStrike": "발 착지 유형",
    "overstriding": "오버스트라이딩",
    "verticalOscillation": "수직 진폭",
    "asymmetry": "좌우 비대칭",
    "coachFeedback": "AI 코칭 피드백",
    "share": "결과 공유",
    "home": "처음으로",
    "lowConfidenceBanner": "참고용 — 재촬영 후 다시 분석해주세요"
  },
  "confidence": {
    "title": "분석 신뢰도",
    "high": "높음",
    "medium": "보통",
    "low": "낮음",
    "warningHeader": "입력 영상 경고"
  },
  "status": {
    "safe": "안전",
    "warning": "경고",
    "danger": "위험"
  },
  "dashboard": {
    "title": "비포/애프터 누적 분석",
    "ptEffect": "PT 효과 요약",
    "empty": "분석 이력이 없습니다."
  }
}
```

---

## 🧪 검증 방법

### 1단계: 결과 화면 시각 검증
- 영상 재생 정상 동작
- 타임라인에 빨간 마커 정확한 위치
- Danger 구간 진입 시 "🐢 0.5x 슬로우 모션" 뱃지 표시
- 색상 뱃지가 상태에 따라 변경

### 2단계: 한국어 메시지 가독성
- 코칭 메시지가 자연스럽게 표시
- 글자 짤림/오버플로우 없음
- 폰트 크기/줄간격 적절

### 3단계: 누적 대시보드 (트레이너 모드)
1. 동일 회원으로 3회 이상 분석
2. DashboardScreen 진입
3. 그래프가 시간순으로 정확히 표시
4. PT 효과 요약 텍스트 정상

### 4단계: 공유 기능
- iOS: 공유 시트 표시
- Android: 인텐트로 카카오톡/이메일 등 선택 가능

### 5단계: end-to-end 시나리오
```
1. 트레이너 로그인 → 모드 토글 ON
2. 회원 등록 ("홍길동")
3. 회원 선택 후 촬영 → 업로드 → 분석 → 결과 확인
4. 동일 회원으로 추가 2회 분석
5. DashboardScreen에서 누적 그래프 확인
6. "Heel Strike 15회 → 3회" 형태로 PT 효과 시각화 확인
```

---

## 💬 추천 Vibe Coding 명령

```
1. "PRD-6-app-result.md를 보고 추가 의존성 설치. react-native-video, react-native-chart-kit, react-native-share 등."

2. "src/hooks/useSlowMotionAtDanger.ts 구현. 현재 시점이 Danger ±0.5초 구간이면 0.5x 자동 전환."

3. "src/components/VideoPlayerWithMarkers.tsx 구현. react-native-video + SVG 타임라인 마커 + 슬로우 모션 뱃지."

4. "src/components/MetricBadge.tsx와 MetricsSummary.tsx 구현. 🔴🟡🟢 색상 뱃지로 4대 지표 표시."

5. "src/components/CoachMessageCard.tsx 구현. 한국어 코칭 메시지 카드형 UI."

6. "src/screens/ResultScreen.tsx 구현. 영상 + 코칭 + 메트릭 요약 + 공유 버튼 통합."

7. "src/components/ProgressChart.tsx 구현. react-native-chart-kit LineChart 활용."

8. "src/screens/DashboardScreen.tsx 구현. /api/members/{id}/history 호출 후 그래프 3개 표시 + PT 효과 요약."

9. "i18n/ko.json에 결과/대시보드 화면 한국어 문자열 추가. App.tsx 네비게이션에 ResultScreen, DashboardScreen 등록."

10. "실기기에서 end-to-end 시나리오 검증. 트레이너 모드 → 회원 등록 → 3회 분석 → 대시보드 확인까지."
```

---

## 📤 산출물

### 생성될 파일
```
app/src/
├── screens/
│   ├── ResultScreen.tsx
│   └── DashboardScreen.tsx
├── components/
│   ├── VideoPlayerWithMarkers.tsx
│   ├── MetricBadge.tsx
│   ├── MetricsSummary.tsx
│   ├── CoachMessageCard.tsx
│   ├── ProgressChart.tsx
│   ├── ConfidenceBadge.tsx       # PRD-8
│   └── WarningList.tsx           # PRD-8
├── hooks/
│   └── useSlowMotionAtDanger.ts
└── i18n/ko.json (업데이트)
```

### 다음 단계로 넘길 인터페이스

**Step 7(통합 테스트)에서 검증할 시나리오**:
- 일반 사용자: 촬영 → 분석 → 결과 확인
- 트레이너: 회원 등록 → 회원별 촬영 → 누적 대시보드 확인
- 분석 소요 시간 측정
- WiFi LAN 안정성 검증

---

## ⚠️ 흔한 함정

1. **react-native-video의 `rate` prop**
   - iOS는 부드럽게 전환되나 Android에서 일부 디바이스 미지원
   - 폴백: `playbackRate` setter 직접 호출

2. **SVG 타임라인 좌표 계산**
   - `duration`이 0일 때 NaN 발생 → 조건부 렌더링 필수
   - `marker.time_sec / duration * SCREEN_W`에서 0 체크

3. **iOS HTTP 영상 로드 차단**
   - `Info.plist`의 `NSAppTransportSecurity` → `NSAllowsArbitraryLoads: true`
   - 운영 환경에서는 HTTPS 필수

4. **차트 라이브러리 데이터 길이**
   - 데이터가 1개뿐이면 차트 깨짐 → 최소 2개 보장
   - `if (history.length < 2)` 분기 처리

5. **공유 기능 시 파일 권한**
   - iOS는 임시 파일 권한 자동
   - Android는 FileProvider 설정 필요

6. **Danger 구간 중첩 시 슬로우 모션 깜빡임**
   - 인접한 Danger 타임스탬프는 병합 권장
   - 또는 디바운스로 1초 미만 변경 무시

7. **한국어 텍스트 줄바꿈**
   - 긴 코칭 메시지는 `numberOfLines` 설정 또는 ScrollView로 감싸기
   - 단어 단위 줄바꿈을 위해 `breakStrategy="balanced"` (Android)

8. **신뢰도 배지/경고 카드를 톤다운 영역 안에 두는 실수** _(2026-05-15, PRD-8)_
   - `low confidence` 면 메트릭 영역을 30% 투명도로 톤다운하는데,
     `ConfidenceBadge` 와 `WarningList` 가 같이 흐려지면 정작 사용자가 봐야 할 경고가 가려짐
   - 두 컴포넌트는 항상 톤다운 래퍼 *바깥에* 둘 것

9. **`warnings` 가 빈 배열일 때 카드 노출** _(2026-05-15)_
   - `confidence: "high"` 면 `warnings: []` 인데, 카드가 "0건" 으로 표시되면 노이즈
   - `WarningList` 에서 `if (warnings.length === 0) return null` 로 사전 차단

10. **신뢰도 색상이 메트릭 색상과 충돌**
    - `MetricBadge` 의 🟢🟡🔴 와 `ConfidenceBadge` 가 같은 색상 토큰을 쓰므로
      배치 시 둘이 한 줄에 나란히 오지 않도록 — `ConfidenceBadge` 는 상단 헤더 영역에만
