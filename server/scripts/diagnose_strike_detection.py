"""
Strike detection 진단 (2026-05-29).

pace530.mp4 의 좌/우 ankle Y 시계열 + 검출된 strike 인덱스를 시각화.
ground truth: 사용자 수동 카운트 25 strikes (전체). 우리 알고리즘 32 strikes.
어디서 over-count 가 발생하는지 (한 stance 안의 double peak, 노이즈, 등) 추적.

부수 산출: cooldown 을 10/20/30/40 프레임으로 바꿨을 때 좌/우 strike 개수 표.
"""
from __future__ import annotations

import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")  # 헤드리스 출력.
import matplotlib.pyplot as plt
import numpy as np

SERVER_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVER_DIR))

from analyzer.foot_strike_detector import detect_foot_strikes  # noqa: E402
from analyzer.pose_extractor import extract_pose_series  # noqa: E402
from analyzer.preprocessor import preprocess_pose_dataframe  # noqa: E402


VIDEO = SERVER_DIR / "pace530.mp4"
GROUND_TRUTH_TOTAL = 25
OUT_DIR = SERVER_DIR / "scripts"


def main() -> None:
    print(f"=== Extracting pose from {VIDEO.name} ===", flush=True)
    raw = extract_pose_series(str(VIDEO))
    df = preprocess_pose_dataframe(raw)
    fps = float(df.attrs.get("fps", 60.0))
    print(f"  frames={len(df)} fps={fps:.2f} duration={len(df)/fps:.2f}s", flush=True)

    left_y = df["left_ankle_y"].to_numpy(dtype=float)
    right_y = df["right_ankle_y"].to_numpy(dtype=float)

    # ---- 1. cooldown 스윕: 강제 cooldown 변경 ----
    print("\n=== Cooldown sweep (frames) ===", flush=True)
    print(f"{'cooldown':<10}{'left':<8}{'right':<8}{'total':<8}{'vs_GT(25)':<10}", flush=True)
    sweep_results = []
    for cd in (5, 10, 15, 20, 25, 30, 40, 50):
        l = detect_foot_strikes(left_y, cooldown=cd)
        r = detect_foot_strikes(right_y, cooldown=cd)
        tot = len(l) + len(r)
        diff = tot - GROUND_TRUTH_TOTAL
        sign = "+" if diff > 0 else ""
        print(f"{cd:<10}{len(l):<8}{len(r):<8}{tot:<8}{sign}{diff:<10}", flush=True)
        sweep_results.append((cd, len(l), len(r), tot))

    # ---- 2. 기본 cooldown=10 시각화 ----
    print("\n=== Default cooldown=10 visualization ===", flush=True)
    left_idx = detect_foot_strikes(left_y, cooldown=10)
    right_idx = detect_foot_strikes(right_y, cooldown=10)
    print(f"  left strikes idx: {left_idx.tolist()}", flush=True)
    print(f"  right strikes idx: {right_idx.tolist()}", flush=True)
    print(f"  total={len(left_idx)+len(right_idx)} vs GT={GROUND_TRUTH_TOTAL}", flush=True)

    t = np.arange(len(df)) / fps

    fig, axes = plt.subplots(2, 1, figsize=(14, 8), sharex=True)
    axes[0].plot(t, left_y, "b-", lw=1.2, label="left_ankle_y")
    axes[0].plot(t[left_idx], left_y[left_idx], "rv", ms=10, label=f"detected strikes (n={len(left_idx)})")
    axes[0].invert_yaxis()  # Y 작을수록 위 = 화면 위. 발 디딤 = 아래 = Y 큼. invert 하면 시각적으로 발이 아래로 가는 게 직관.
    axes[0].set_ylabel("left ankle Y (norm, inverted)")
    axes[0].legend(loc="upper right")
    axes[0].set_title(f"pace530.mp4 — left ankle Y + detected strikes (cooldown=10, fps={fps:.1f})")
    axes[0].grid(True, alpha=0.3)

    axes[1].plot(t, right_y, "g-", lw=1.2, label="right_ankle_y")
    axes[1].plot(t[right_idx], right_y[right_idx], "rv", ms=10, label=f"detected strikes (n={len(right_idx)})")
    axes[1].invert_yaxis()
    axes[1].set_ylabel("right ankle Y (norm, inverted)")
    axes[1].set_xlabel("time (s)")
    axes[1].legend(loc="upper right")
    axes[1].set_title(f"pace530.mp4 — right ankle Y + detected strikes (cooldown=10)")
    axes[1].grid(True, alpha=0.3)

    out_png = OUT_DIR / "diagnose_strike_detection_pace530.png"
    fig.tight_layout()
    fig.savefig(out_png, dpi=120)
    print(f"\n  saved: {out_png}", flush=True)

    # ---- 3. 인접 strike 간격 분포 (frames) ----
    print("\n=== Inter-strike intervals (frames, cooldown=10) ===", flush=True)
    for name, idx in (("left", left_idx), ("right", right_idx)):
        if len(idx) >= 2:
            gaps = np.diff(idx)
            print(
                f"  {name}: n={len(idx)} gaps min/median/max = "
                f"{gaps.min()}/{int(np.median(gaps))}/{gaps.max()} frames "
                f"({gaps.min()/fps*1000:.0f}/{int(np.median(gaps))/fps*1000:.0f}/{gaps.max()/fps*1000:.0f} ms)",
                flush=True,
            )
            # 너무 짧은 간격 = double peak 의심.
            short = gaps[gaps < 20]
            if len(short):
                print(f"    -> {len(short)} gaps < 20 frames (333ms) — double peak 의심: {short.tolist()}", flush=True)

    print("\nDone.")


if __name__ == "__main__":
    main()
