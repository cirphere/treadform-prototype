"""
4영상 prominence sweep (2026-05-29).

boundary trim (B 안 롤백) 대신 prominence 임계로 boundary spurious peak 만
거를 수 있는지 검증. cd=20 + min_prominence sweep → 각 영상에서
1) 정상 strike 의 prominence 분포 (min/med/max)
2) min_prominence 값별 strike 개수
3) plateau 위치 → 안전 임계 후보

목표: 4영상 모두 정상 strike 손실 없이 spurious 만 거르는 plateau.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from scipy.signal import find_peaks

SERVER_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVER_DIR))

from analyzer.pose_extractor import extract_pose_series  # noqa: E402
from analyzer.preprocessor import preprocess_pose_dataframe  # noqa: E402


VIDEOS = {
    "pace530.mp4": 25,
    "pace6.mp4":   67,
    "pace630.mp4": 45,
    "pace7.mp4":   33,
}

COOLDOWN = 20
THRESHOLDS = (0.0, 0.001, 0.005, 0.01, 0.015, 0.02, 0.025, 0.03, 0.04, 0.05)


def side_analysis(y: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    sentinel = np.nanmin(y) - 1.0 if np.isfinite(np.nanmin(y)) else -1.0
    sanitized = np.where(np.isnan(y), sentinel, y)
    peaks, props = find_peaks(sanitized, distance=COOLDOWN, prominence=0)
    # NaN 위치 제거.
    valid = ~np.isnan(y[peaks])
    return peaks[valid], props["prominences"][valid]


def main() -> None:
    all_results = []
    for name, gt in VIDEOS.items():
        path = SERVER_DIR / name
        print(f"\n=== {name} (GT={gt}) ===", flush=True)
        raw = extract_pose_series(str(path))
        df = preprocess_pose_dataframe(raw)
        fps = float(df.attrs.get("fps", 60.0))
        duration = len(df) / fps
        print(f"  frames={len(df)} fps={fps:.2f} duration={duration:.2f}s", flush=True)

        left_y = df["left_ankle_y"].to_numpy(dtype=float)
        right_y = df["right_ankle_y"].to_numpy(dtype=float)
        l_peaks, l_proms = side_analysis(left_y)
        r_peaks, r_proms = side_analysis(right_y)

        print(f"  baseline (prom>=0): L={len(l_peaks)} R={len(r_peaks)} tot={len(l_peaks)+len(r_peaks)}", flush=True)
        for label, proms in (("L", l_proms), ("R", r_proms)):
            if len(proms):
                print(f"    {label} prominence: min={proms.min():.4f} "
                      f"5th={np.percentile(proms, 5):.4f} "
                      f"med={np.median(proms):.4f} "
                      f"max={proms.max():.4f}", flush=True)

        print(f"  {'min_prom':<10}{'L':<5}{'R':<5}{'tot':<6}{'vs_GT':<8}{'spm':<7}", flush=True)
        per_thresh = {}
        for th in THRESHOLDS:
            l_n = int((l_proms >= th).sum())
            r_n = int((r_proms >= th).sum())
            tot = l_n + r_n
            diff = tot - gt
            spm = tot / duration * 60.0 if duration > 0 else 0.0
            sign = "+" if diff > 0 else ""
            print(f"  {th:<10.4f}{l_n:<5}{r_n:<5}{tot:<6}{sign}{diff:<7}{spm:<7.1f}", flush=True)
            per_thresh[th] = (l_n, r_n, tot, spm)

        all_results.append({"name": name, "gt": gt, "duration": duration, "per_thresh": per_thresh})

    print("\n\n=== Cross-video summary: total strikes by min_prominence ===", flush=True)
    header = f"{'min_prom':<10}" + "".join(f"{r['name']:<14}" for r in all_results)
    print(header, flush=True)
    gt_row = f"{'GT':<10}" + "".join(f"{str(r['gt']):<14}" for r in all_results)
    print(gt_row, flush=True)
    for th in THRESHOLDS:
        row = f"{th:<10.4f}"
        for r in all_results:
            _, _, tot, spm = r["per_thresh"][th]
            row += f"{f'{tot} ({spm:.0f})':<14}"
        print(row, flush=True)


if __name__ == "__main__":
    main()
