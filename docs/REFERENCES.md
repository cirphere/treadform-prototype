# TreadForm 학술 참고문헌

> 본 문서는 TreadForm 분석 엔진의 임계값/설계 결정을 뒷받침하는 **1차 출처 목록**이다.
> 각 항목은 PubMed/PMC/arXiv 에서 직접 확인하여 검증되었다 (2026-05-17).
>
> - 각 임계값과 출처의 매핑은 [PRD-2-metrics.md](./PRD-2-metrics.md) 의 `📚 학술 근거 / References` 와 [PRD-8-video-input-spec.md](./PRD-8-video-input-spec.md) 의 `📚 학술 근거 / References` 섹션 참조.
> - 코드 (`server/config.py`) 에서는 임계값별로 짧은 `[Ref]` 포인터를 주석에 표기.

---

## 검증 상태

| # | 출처 | 검증 경로 | 상태 |
|---|------|----------|------|
| R1 | Heiderscheit 2011 MSSE | PMC3022995 (full text) | ✅ |
| R2-1 | Altman & Davis 2012 Gait Posture | PMC3278526 | ✅ |
| R2-2 | Lieberman 2010 Nature | PubMed 20111000 | ✅ |
| R3 | Schubert 2014 Sports Health | PubMed 24790690, PMC4000471 | ✅ |
| R4-1 | Tartaruga 2012 RQES | PubMed 22978185 | ✅ |
| R4-2 | Folland 2017 MSSE | PubMed 28263283, PMC5473370 | ✅ |
| R4-3 | Cavanagh & Williams 1982 MSSE | PubMed 7070254 | ✅ |
| R5-1 | Zifchock 2008 Gait Posture | PubMed 17913499 | ✅ |
| R5-2 | Zifchock 2006 J Biomech | PubMed 16289516 | ✅ |
| R5-3 | Pappas et al. 2015 Hum Mov Sci | PubMed 25625812 | ✅ |
| R5-4 | Parkinson et al. 2021 J Sports Sci Med | PubMed 35321131 / PMC8488821 | ✅ |
| R7 | Bazarevsky 2020 BlazePose | arXiv 2006.10204 | ✅ |
| V5-1 | Cavanagh & Kram 1989 MSSE | PubMed 2674599 | ✅ |
| V5-2 | Daniels' Running Formula 4ed | Human Kinetics, ISBN 978-1492570677 | 📖 (단행본) |

---

## R1. 무릎 굴곡 (Knee Flexion)

### Heiderscheit BC, Chumanov ES, Michalski MP, Wille CMA, Ryan MB.
> **Effects of step rate manipulation on joint mechanics during running.**
> *Medicine & Science in Sports & Exercise.* 2011;43(2):296-302.
> DOI: [10.1249/MSS.0b013e3181ebedf4](https://doi.org/10.1249/MSS.0b013e3181ebedf4)
> PMID: [20581720](https://pubmed.ncbi.nlm.nih.gov/20581720/) · PMC: [PMC3022995](https://pmc.ncbi.nlm.nih.gov/articles/PMC3022995/)

**Key finding (메커니즘 근거):** Cadence 를 preferred 대비 +5% / +10% 로 올렸을 때 무릎 에너지 흡수가 각각 ~20% / ~34% 감소. IC 및 peak knee flexion 변동성을 함께 다루며, stiff knee 패턴이 shock absorption 부족과 직접 연결됨을 정량.

**Key finding (정량 normative 근거, 2026-05-25 추가):** 동일 논문이 보고한 n=45 healthy recreational runner 의 condition 별 IC knee flexion 측정값:

| Condition | IC knee flexion (deg) |
|---|---|
| **Preferred (baseline)** | **17.8 ± 4.0** |
| +5% step rate | 18.7 ± 3.9 |
| +10% step rate | 19.6 ± 4.2 (p<0.01) |
| −5% step rate | 17.0 ± 4.1 |
| −10% step rate | 16.9 ± 4.2 |

측정 정의: IC = "vertical GRF > 50 N 인 순간" (포스플레이트 trigger), 200 Hz 8-camera 3D motion capture.

**우리 임계의 SD 단위 매핑:** Heiderscheit 컨벤션 (0° = straight leg) ↔ 우리 컨벤션 (180° = straight leg).

| 우리 knee angle | = IC flexion | Heiderscheit baseline (17.8 ± 4.0) 기준 |
|---|---|---|
| 158.2° | 21.8° | mean + 1 SD (더 굽힘) |
| 162.2° | 17.8° | mean (baseline) |
| **165°** (stiff 임계) | **15°** | **mean − 0.7 SD (덜 굽힘, statistical outlier-leaning)** |
| 166.2° | 13.8° | mean − 1 SD |
| 140° (over_bent 임계) | 40° | mean + 5.6 SD (매우 보수적 하한) |

→ 우리 stiff 임계 165° 는 Heiderscheit baseline 의 평균보다 약 0.7 SD stiffer 영역에 위치 — 통계적으로 합리적 outlier 경계.

**자체 데이터 검증:** pace 530/6/7/630 4 영상 200 strikes 평균 knee angle 158.5° (IC flexion 21.5°, baseline 보다 0.9 SD 더 굽힘 — 숙련 러너의 우수한 mechanics 와 일관). Max 164° (mean − 0.45 SD), > 165° 진입 0건, < 140° 진입 0건. False positive 0건 확인.

> **Souza 2016 위치 — 향후 작업 인용 예정 (2026-05-25 재정리):** Souza RB. *Phys Med Rehabil Clin N Am.* 2016;27(1):217-236 (PMC4714754) 의 "knee flexion < 45° = stiff" 임계는 **stance phase peak flexion** (mid-stance 최대 굴곡) 기준이며, 현재 우리 측정은 IC 시점만 평가하므로 적용 불가. 향후 **Peak Flexion 지표 추가** 시 1차 근거로 복귀 예정 — toe-off 검출 + stance phase slicing 구현 필요, 60fps 에서 peak 시점 시간 분해능 ±3° 한계. PRD-2 §[R1-future] 참조.

---

## R2. Foot Strike Pattern

### Altman AR, Davis IS.
> **A kinematic method for footstrike pattern detection in barefoot and shod runners.**
> *Gait & Posture.* 2012;35(2):298-300.
> DOI: [10.1016/j.gaitpost.2011.09.104](https://doi.org/10.1016/j.gaitpost.2011.09.104)
> PMC: [PMC3278526](https://pmc.ncbi.nlm.nih.gov/articles/PMC3278526/)

**Key finding:** Foot Strike Angle (FSA) — sagittal plane 에서 발과 지면의 각도. FSA > 0° = rearfoot strike (RFS), < 0° = forefoot/midfoot strike. Strike Index 와 R=0.92 강한 상관. 우리 측정 방식 (`heel→foot_index` 벡터 수평 기준 기울기)의 분류 표준.

**자체 결정 명시 ⚠️:** Altman & Davis 의 cutoff 는 정확히 0°. 우리 임계 ±3° 는 **2D 영상 perspective + 발 길이 정규화 노이즈에 대한 안전 마진** (자체 결정). 임상 분류 관행 (±2~3°) 에 정합 — 2026-05-17 보수성 축소 (±5° → ±3°).

### Lieberman DE, Venkadesan M, Werbel WA, Daoud AI, D'Andrea S, Davis IS, Mang'eni RO, Pitsiladis Y.
> **Foot strike patterns and collision forces in habitually barefoot versus shod runners.**
> *Nature.* 2010;463(7280):531-535.
> DOI: [10.1038/nature08723](https://doi.org/10.1038/nature08723)
> PMID: [20111000](https://pubmed.ncbi.nlm.nih.gov/20111000/)

**Key finding:** 측정 대상 (맨발/슈드 러너 그룹별) 의 footstrike 차이와 collision force 정량. RFS는 명확한 impact peak (~3× 체중) 생성, FFS/MFS는 충격 분산 가능. heel strike 가 부상 위험과 직접 연결됨을 보인 대표 연구.

---

## R3. Overstriding

### Schubert AG, Kempf J, Heiderscheit BC.
> **Influence of stride frequency and length on running mechanics: a systematic review.**
> *Sports Health.* 2014;6(3):210-217.
> DOI: [10.1177/1941738113508544](https://doi.org/10.1177/1941738113508544)
> PMID: [24790690](https://pubmed.ncbi.nlm.nih.gov/24790690/) · PMC: [PMC4000471](https://pmc.ncbi.nlm.nih.gov/articles/PMC4000471/)

**Key finding:** Stride length 증가 → hip/knee extension moment 유의 증가, rearfoot 각속도 증가 → tibial stress fracture 위험과 강한 연관. Stride length 감소 (= cadence 증가) 가 부상 예방의 핵심 lever.

### Heiderscheit BC et al. 2011 MSSE
(R1 참조) — Step length 감소가 hip/knee loading 동시 감소. COM vertical excursion 도 감소.

**우리 임계 0.15 (정규화 좌표):** 1280×720 측면 영상의 자체 결정. PRD-8 촬영 가이드 (피사체가 화면 60~80% 점유) 가정 하 임상 절대 거리 (cm) 대비 보수적.

---

## R4. Vertical Oscillation

### Tartaruga MP, Brisswalter J, Peyré-Tartaruga LA, et al.
> **The Relationship Between Running Economy and Biomechanical Variables in Distance Runners.**
> *Research Quarterly for Exercise and Sport.* 2012;83(3):367-375.
> DOI: [10.1080/02701367.2012.10599870](https://doi.org/10.1080/02701367.2012.10599870)
> PMID: [22978185](https://pubmed.ncbi.nlm.nih.gov/22978185/)

**Key finding:** Vertical oscillation 과 running economy 의 유의한 음의 상관. 16명 long-distance runner submaximal pace 검증.

### Folland JP, Allen SJ, Black MI, Handsaker JC, Forrester SE.
> **Running Technique is an Important Component of Running Economy and Performance.**
> *Medicine & Science in Sports & Exercise.* 2017;49(7):1412-1423.
> DOI: [10.1249/MSS.0000000000001245](https://doi.org/10.1249/MSS.0000000000001245)
> PMID: [28263283](https://pubmed.ncbi.nlm.nih.gov/28263283/) · PMC: [PMC5473370](https://pmc.ncbi.nlm.nih.gov/articles/PMC5473370/)

**Key finding:** 97명 endurance runner 대상, VO 가 modifiable 한 핵심 economy 결정 변수임을 검증. 3개 변수 조합이 locomotory energy cost 의 39% 설명.

### Cavanagh PR, Williams KR.
> **The effect of stride length variation on oxygen uptake during distance running.**
> *Medicine & Science in Sports & Exercise.* 1982;14(1):30-35.
> PMID: [7070254](https://pubmed.ncbi.nlm.nih.gov/7070254/)

**Key finding:** Preferred stride length 가 oxygen cost 를 최소화하는 위치에 자연스럽게 위치함을 검증. ±20% 변동 시 모두 oxygen uptake 상승. VO 측정 방법론의 고전 문헌.

**우리 임계 0.06 (정규화 Y):** 신장 1.7m + PRD-8 촬영 가이드 (인체 화면 60~80% 점유) 기준 약 10cm — **healthy upper bound 와 정합** (2026-05-17 0.08 → 0.06 으로 학술 통념에 맞춰 축소).

---

## R5. Bilateral Asymmetry

### Zifchock RA, Davis I, Higginson J, Royer T.
> **The symmetry angle: a novel, robust method of quantifying asymmetry.**
> *Gait & Posture.* 2008;27(4):622-627.
> DOI: [10.1016/j.gaitpost.2007.08.006](https://doi.org/10.1016/j.gaitpost.2007.08.006)
> PMID: [17913499](https://pubmed.ncbi.nlm.nih.gov/17913499/)

**Key finding:** Symmetry Angle (SA) 도입 — `SA = (45° − arctan(X_L / X_R)) / 90° × 100%`. 기존 Symmetry Index 의 reference value 의존성 단점 해결. 10% 임계가 임상적으로 의미있는 비대칭의 기준점으로 자주 인용됨.

### Zifchock RA, Davis I, Hamill J.
> **Kinetic asymmetry in female runners with and without retrospective tibial stress fractures.**
> *Journal of Biomechanics.* 2006;39(15):2792-2797.
> DOI: [10.1016/j.jbiomech.2005.10.003](https://doi.org/10.1016/j.jbiomech.2005.10.003)
> PMID: [16289516](https://pubmed.ncbi.nlm.nih.gov/16289516/)

**Key finding:** 부상 이력 (tibial stress fracture) 여부와 ground reaction force 비대칭 분포 비교. healthy 러너에서도 자연 비대칭이 변수마다 3.1% ~ 49.8% 분포 — 임계 설정 시 단일 절대값 적용 한계를 시사.

### Pappas P, Paradisis G, Vagenas G.
> **Leg and vertical stiffness (a)symmetry between dominant and non-dominant legs in young male runners.**
> *Human Movement Science.* 2015;40:273-283.
> DOI: [10.1016/j.humov.2015.01.005](https://doi.org/10.1016/j.humov.2015.01.005)
> PMID: [25625812](https://pubmed.ncbi.nlm.nih.gov/25625812/)

**Key finding:** 22명 healthy 남성 러너 ASI 정량. **healthy 자연 ASI 는 GRF 1.81% / contact time 2.83% / leg stiffness 6.38% 수준** — 즉 10% 임계는 healthy 분포 너머의 임상 의미 있는 비대칭 신호. 우리 임계의 강한 학술 매칭 (2026-05-17 추가).

### Parkinson AO, Apps CL, Morris JG, Barnett CT, Lewis MGC.
> **The Calculation, Thresholds and Reporting of Inter-Limb Strength Asymmetry: A Systematic Review.**
> *Journal of Sports Science and Medicine.* 2021;20(4):594-617.
> DOI: [10.52082/jssm.2021.594](https://doi.org/10.52082/jssm.2021.594)
> PMID: [35321131](https://pubmed.ncbi.nlm.nih.gov/35321131/) · PMC: [PMC8488821](https://pmc.ncbi.nlm.nih.gov/articles/PMC8488821/)

**Key finding:** 18편 문헌 메타분석 결과 **15편이 10~15% 임계를 채택** — 임상 합의 수준임을 시스템적으로 확인 (2026-05-17 추가).

---

## R6. 비대칭 트리거 격하 + Visibility 가중 (자체 데이터 검증)

**1차 출처 없음 — 자체 측정 데이터 기반 설계 결정 (2026-05-17).**

같은 숙련 러너의 4 페이스 (530/6/7/630) 측면 영상 분석 결과:

| 영상 | strike L/R | strike ratio | knee ratio | osc ratio | foot vis L/R |
|------|-----------|-----|------|------|-----|
| pace530 | 15 / 17 | 11.8% | 0.5% | 2.2% | 0.876 / 0.963 |
| pace7   | 16 / 19 | 15.8% | 1.8% | 8.5% | 0.882 / 0.964 |
| pace6   | 40 / 40 | 0.0% | 0.0% | 3.9% | 0.878 / 0.966 |
| pace630 | 25 / 28 | 10.7% | 1.3% | 3.4% | 0.882 / 0.966 |

**관측:** 카메라 가까운 발(우) visibility 0.96 / 먼 발(좌) visibility 0.88 — 일관된 occlusion 패턴. strike count 비대칭이 10~16% 발생하지만 knee/osc 는 모두 ≤2% (정상). 즉 strike count 비대칭은 측면 촬영 구조적 노이즈가 dominant 신호.

**설계 결정:**
1. `is_warning` 트리거에서 strike_count_ratio 제외 (knee/osc 만 사용).
2. 좌/우 발 평균 visibility diff > 0.10 시 strike_count_ratio → NaN (검출 불가능 신호).

**이론적 배경:** BlazePose 의 `visibility` 출력은 frame-별 키포인트 검출 신뢰도이며, occluded landmark 는 visibility 가 떨어지므로 한쪽이 일관되게 낮은 영상에서는 해당 측 strike 검출이 누락될 가능성이 높다 → 카운트 비대칭이 실제 비대칭이 아닌 검출 누락의 결과.

---

## R7. MediaPipe BlazePose

### Bazarevsky V, Grishchenko I, Raveendran K, Zhu T, Zhang F, Grundmann M.
> **BlazePose: On-device Real-time Body Pose Tracking.**
> *arXiv preprint arXiv:[2006.10204](https://arxiv.org/abs/2006.10204).* 2020.
> Presented at: CV4ARVR Workshop, CVPR 2020.

**Key finding:** 33-keypoint 토폴로지 (BlazePose) 가 COCO + BlazeFace + BlazePalm 의 superset. HEEL/FOOT_INDEX 포함 — 우리 foot strike 측정의 필수 키포인트. OpenPose 대비 25-75× 빠르면서 AR/fitness 도메인 정확도 유지. PRD-0 의 모델 선택 (model_complexity=2, Heavy) 근거.

---

## V5. Cadence 표준 (180 spm)

### Cavanagh PR, Kram R.
> **Stride length in distance running: velocity, body dimensions, and added mass effects.**
> *Medicine & Science in Sports & Exercise.* 1989;21(4):467-479.
> PMID: [2674599](https://pubmed.ncbi.nlm.nih.gov/2674599/)

**Key finding:** Recreational distance runner 의 preferred stride frequency 가 속도 증가에 거의 무관 (속도 +30% 시 cadence +4%, stride length +28%). 개인별 economy-optimal stride frequency 가 존재함을 정량 검증.

### Daniels J.
> ***Daniels' Running Formula.*** 4th ed.
> Human Kinetics; 2021. ISBN 978-1492570677.

**Key finding (원판 1998):** 1984 LA Olympics 엘리트 distance runner 46명 cadence 관측 — 단 1명만 180 spm 미만 (176 spm). "180 spm" 통념의 출처. 단, 페이스 의존성 (race pace 기준) 으로 recreational runner 에 그대로 적용 불가.

**우리 임계 `WARN_HIGH_CADENCE_SPM = 190`:** 일반 권장 180 + 안전 마진. 30fps 영상에서 모션 블러 위험이 dominant 해지는 경계.

---

## 인용 가이드 (발표 자료용)

발표 슬라이드에서 inline 인용 예시:

> 우리는 무릎 굴곡 임계값을 hip-knee-ankle 내각 **165°(stiff) / 140°(over-bent)** 로 정의했습니다 (2026-05-25 재조정).
> 이는 **Heiderscheit et al. (2011)¹** 의 IC knee flexion baseline 측정값 **17.8° ± 4.0°** (n=45 healthy recreational runner) 에 기반하며, 우리 stiff 임계 165° (= IC flexion 15°) 는 해당 baseline 평균보다 약 0.7 SD stiffer 영역에 해당합니다.
> 동일 논문이 추가로 stiff knee 패턴 (낮은 IC flexion) 이 shock absorption 부족과 부상 위험에 직접 연결됨을 정량했습니다.
> 우리 측정은 IC 시점만 평가하며, mid-stance peak flexion 측정 (Souza 2016 권장) 은 향후 작업으로 deferred 상태입니다 (PRD-2 §[R1-future]).

References slide 예시:

1. Heiderscheit BC et al. *Med Sci Sports Exerc.* 2011;43(2):296-302.
2. Altman AR, Davis IS. *Gait Posture.* 2012;35(2):298-300.
3. Lieberman DE et al. *Nature.* 2010;463:531-535.
4. Schubert AG et al. *Sports Health.* 2014;6(3):210-217.
5. Tartaruga MP et al. *Res Q Exerc Sport.* 2012;83(3):367-375.
6. Folland JP et al. *Med Sci Sports Exerc.* 2017;49(7):1412-1423.
7. Cavanagh PR, Williams KR. *Med Sci Sports Exerc.* 1982;14(1):30-35.
8. Zifchock RA et al. *Gait Posture.* 2008;27(4):622-627.
9. Zifchock RA, Davis I, Hamill J. *J Biomech.* 2006;39(15):2792-2797.
10. Pappas P, Paradisis G, Vagenas G. *Hum Mov Sci.* 2015;40:273-283.
11. Parkinson AO et al. *J Sports Sci Med.* 2021;20(4):594-617.
12. Cavanagh PR, Kram R. *Med Sci Sports Exerc.* 1989;21(4):467-479.
13. Daniels J. *Daniels' Running Formula.* 4th ed. Human Kinetics; 2021.
14. Bazarevsky V et al. arXiv:2006.10204. 2020. (CVPR 2020 CV4ARVR Workshop)

> **Deferred (향후 작업 시 인용 예정):**
> - Souza RB. An evidence-based videotaped running biomechanics analysis. *Phys Med Rehabil Clin N Am.* 2016;27(1):217-236. PMC4714754. — Peak Flexion 지표 추가 시 1차 근거 예정.

---

## 검증 방법

각 항목은 다음 순서로 1차 출처 직접 검증:
1. **DOI resolver** (doi.org) → 공식 publisher 페이지 redirect 확인.
2. **PubMed/PMC** 직접 fetch → 저자/제목/저널/연도/페이지 일치 확인.
3. **arXiv** 직접 확인 (BlazePose).
4. 페이지 paywall 등으로 publisher 직접 접근 불가시 PubMed 메타데이터로 cross-check.

검증 일자: **2026-05-17**.
