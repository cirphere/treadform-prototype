"""
pace630 잔여 +3 over-count 진단 (2026-05-29).

cd=20~40 plateau 에서 우리는 48 strikes 검출, GT 45. 3 false peak 가
cooldown 으론 제거 안 됨 → 한 stance 안의 double peak 가 아니라 별도 위치에
가까운 amplitude 로 존재. prominence/width 임계로 거를 수 있는지 확인.

산출:
- left/right 각 strike 의 prominence + width (find_peaks 추가 출력)
- prominence 분포 + cutoff 가 GT (45) 매치 가능한지
- Y 시계열 + 검출 strike (큰 점) + 작은 prominence peak (작은 점) 시각화 PNG
"""
from __future__ import annotations

import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from scipy.signal import find_peaks

SERVER_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVER_DIR))

from analyzer.pose_extractor import extract_pose_series  # noqa: E402
from analyzer.preprocessor import preprocess_pose_dataframe  # noqa: E402


VIDEO = SERVER_DIR / "pace630.mp4"
GT_TOTAL = 45  # 좌우 합산
COOLDOWN = 20  # 새 default
OUT_DIR = SERVER_DIR / "scripts"


def analyze_side(name: str, y: np.ndarray, fps: float) -> dict:
    sentinel = np.nanmin(y) - 1.0 if np.isfinite(np.nanmin(y)) else -1.0
    sanitized = np.where(np.isnan(y), sentinel, y)
    peaks, props = find_peaks(sanitized, distance=COOLDOWN, prominence=0)
    proms = props["prominences"]

    print(f"\n  --- {name} ankle ---", flush=True)
    print(f"  detected n={len(peaks)} (cd={COOLDOWN}, prominence>=0)", flush=True)
    if len(peaks):
        print(f"  prominence: min={proms.min():.4f} median={np.median(proms):.4f} "
              f"max={proms.max():.4f}", flush=True)
        # 정렬해서 가장 작은 5개 출력 — false peak 후보.
        order = np.argsort(proms)
        print(f"  smallest 5 prominences (frame_idx, t_sec, prom):", flush=True)
        for i in order[:5]:
            print(f"    frame={peaks[i]:4d}  t={peaks[i]/fps:6.2f}s  prom={proms[i]:.4f}", flush=True)

    return {"peaks": peaks, "proms": proms, "y": y}


def sweep_prominence(y: np.ndarray, name: str) -> None:
    print(f"\n  --- {name} prominence sweep ---", flush=True)
    print(f"  {'min_prom':<12}{'n':<6}", flush=True)
    sentinel = np.nanmin(y) - 1.0 if np.isfinite(np.nanmin(y)) else -1.0
    sanitized = np.where(np.isnan(y), sentinel, y)
    for p in (0.0, 0.001, 0.002, 0.003, 0.005, 0.008, 0.01, 0.015, 0.02, 0.03):
        peaks, _ = find_peaks(sanitized, distance=COOLDOWN, prominence=p)
        print(f"  {p:<12.4f}{len(peaks):<6}", flush=True)


def main() -> None:
    print(f"=== Extracting {VIDEO.name} ===", flush=True)
    raw = extract_pose_series(str(VIDEO))
    df = preprocess_pose_dataframe(raw)
    fps = float(df.attrs.get("fps", 60.0))
    duration = len(df) / fps
    print(f"  frames={len(df)} fps={fps:.2f} duration={duration:.2f}s", flush=True)

    left_y = df["left_ankle_y"].to_numpy(dtype=float)
    right_y = df["right_ankle_y"].to_numpy(dtype=float)

    left = analyze_side("left", left_y, fps)
    right = analyze_side("right", right_y, fps)
    print(f"\n  total={len(left['peaks']) + len(right['peaks'])} vs GT={GT_TOTAL}", flush=True)

    sweep_prominence(left_y, "left")
    sweep_prominence(right_y, "right")

    # 시각화 — Y 시계열 + 큰 점 (모든 peak) + prominence 가장 작은 것들 강조.
    t = np.arange(len(df)) / fps
    fig, axes = plt.subplots(2, 1, figsize=(16, 9), sharex=True)

    for ax, side, color in ((axes[0], left, "b"), (axes[1], right, "g")):
        ax.plot(t, side["y"], f"{color}-", lw=1.0, alpha=0.6, label=f"{color} ankle Y")
        ax.plot(t[side["peaks"]], side["y"][side["peaks"]], "rv", ms=8,
                label=f"detected (n={len(side['peaks'])})")
        # 가장 작은 prominence 3개 강조 — 후보 false peak.
        order = np.argsort(side["proms"])
        weak = side["peaks"][order[:3]]
        ax.plot(t[weak], side["y"][weak], "o", mfc="none", mec="orange",
                ms=18, mew=2, label="weakest 3 prom (suspect)")
        ax.invert_yaxis()
        ax.legend(loc="upper right")
        ax.grid(True, alpha=0.3)

    axes[0].set_title(f"pace630 left ankle Y (cd={COOLDOWN}, fps={fps:.0f}) — orange ring = lowest prominence")
    axes[1].set_title("pace630 right ankle Y")
    axes[1].set_xlabel("time (s)")
    fig.tight_layout()
    out_png = OUT_DIR / "diagnose_pace630_residual.png"
    fig.savefig(out_png, dpi=110)
    print(f"\n  saved: {out_png}", flush=True)


if __name__ == "__main__":
    main()
