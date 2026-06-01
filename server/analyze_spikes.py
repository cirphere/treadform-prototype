"""
3단계 좌표(raw / despiked / preprocessed) 의 spike 통계 비교.

각 landmark 의 frame-to-frame 변화량 |x[t] - x[t-1]| 분포를 분석.
'spike' 정의: 변화량이 해당 landmark 의 95퍼센타일을 N배 초과하는 프레임.
"""
from __future__ import annotations

import logging
import sys
from collections import defaultdict
from pathlib import Path

import cv2
import numpy as np
import pandas as pd

from analyzer.pose_extractor import PoseLandmark, extract_pose_series
from analyzer.preprocessor import despike_pose_dataframe, preprocess_pose_dataframe


SPIKE_MULTIPLIER = 3.0  # 95퍼센타일의 N배 이상 변화 → spike 후보
TOP_K_FRAMES = 6        # 시각 검증용으로 추출할 raw spike 상위 프레임 수


def _coord_columns(df: pd.DataFrame) -> list[str]:
    return [c for c in df.columns if c.endswith(("_x", "_y"))]


def _velocity_stats(
    df: pd.DataFrame, fixed_thresholds: dict[str, float] | None = None
) -> dict:
    """
    landmark 별 |Δ|의 분포 + spike 카운트.

    Args:
        df: 좌표 DataFrame.
        fixed_thresholds: 외부에서 받은 컬럼별 임계값. None 이면 자체 p95 사용.
            세 단계 비교 시에는 raw 의 임계값을 고정해 넘긴다.
    """
    cols = _coord_columns(df)
    total_spikes = 0
    total_samples = 0
    max_spike = 0.0
    per_landmark = {}
    spike_frames: list[tuple[int, str, float]] = []
    thresholds_used: dict[str, float] = {}

    for col in cols:
        arr = df[col].to_numpy(dtype=float)
        diff = np.abs(np.diff(arr))
        valid = diff[~np.isnan(diff)]
        if valid.size < 10:
            continue
        if fixed_thresholds is not None:
            thr = fixed_thresholds.get(col, float("inf"))
        else:
            p95 = float(np.percentile(valid, 95))
            thr = p95 * SPIKE_MULTIPLIER
        thresholds_used[col] = thr
        if thr <= 0 or np.isnan(thr) or np.isinf(thr):
            per_landmark[col] = {
                "threshold": thr,
                "spikes": 0,
                "max_velocity": float(np.nanmax(diff)) if valid.size else 0.0,
            }
            total_samples += int(valid.size)
            continue
        spike_mask = diff > thr
        n_spikes = int(np.sum(spike_mask))
        total_spikes += n_spikes
        total_samples += int(valid.size)
        if n_spikes:
            max_spike = max(max_spike, float(diff[spike_mask].max()))
            for idx in np.where(spike_mask)[0]:
                spike_frames.append((int(idx + 1), col, float(diff[idx])))
        per_landmark[col] = {
            "threshold": thr,
            "spikes": n_spikes,
            "max_velocity": float(np.nanmax(diff)) if valid.size else 0.0,
        }

    return {
        "total_spikes": total_spikes,
        "total_samples": total_samples,
        "max_spike_velocity": max_spike,
        "per_landmark": per_landmark,
        "spike_frames": sorted(spike_frames, key=lambda x: -x[2]),
        "thresholds": thresholds_used,
    }


def _save_frame_png(video_path: Path, frame_idx: int, out_path: Path) -> None:
    cap = cv2.VideoCapture(str(video_path))
    cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
    ok, frame = cap.read()
    cap.release()
    if ok:
        cv2.imwrite(str(out_path), frame)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    here = Path(__file__).parent
    video = Path(sys.argv[1]) if len(sys.argv) > 1 else here / "running_video.mp4"

    print(f"[INFO] analyzing: {video}")
    raw = extract_pose_series(str(video))
    despiked = despike_pose_dataframe(raw)
    final = preprocess_pose_dataframe(raw)

    print(f"[INFO] frames: {len(raw)}, coord columns: {len(_coord_columns(raw))}")
    print(f"[INFO] spike threshold: > {SPIKE_MULTIPLIER}x 95-percentile of |Δ|\n")

    # raw 의 임계값을 고정해 despiked/final 에 동일하게 적용.
    raw_stats = _velocity_stats(raw)
    fixed_thr = raw_stats["thresholds"]
    despiked_stats = _velocity_stats(despiked, fixed_thresholds=fixed_thr)
    final_stats = _velocity_stats(final, fixed_thresholds=fixed_thr)
    results = {"raw": raw_stats, "despiked": despiked_stats, "final": final_stats}

    for name in ("raw", "despiked", "final"):
        st = results[name]
        rate = st["total_spikes"] / max(st["total_samples"], 1) * 100
        print(
            f"=== {name.upper():<9} | spikes: {st['total_spikes']:>4d} "
            f"({rate:.2f}%) | max |Δ|: {st['max_spike_velocity']:.4f}"
        )

    print()
    print("=== Top 10 spike-prone landmarks (raw) ===")
    raw_per = results["raw"]["per_landmark"]
    sorted_lm = sorted(raw_per.items(), key=lambda x: -x[1]["spikes"])
    print(f"{'landmark':<28} {'spikes':>7} {'thr':>10} {'max|Δ|':>10}")
    for name, st in sorted_lm[:10]:
        print(f"{name:<28} {st['spikes']:>7d} {st['threshold']:>10.4f} {st['max_velocity']:>10.4f}")

    print()
    print("=== Reduction (raw → despiked → final) ===")
    r, d, f = results["raw"]["total_spikes"], results["despiked"]["total_spikes"], results["final"]["total_spikes"]
    r_max = results["raw"]["max_spike_velocity"]
    d_max = results["despiked"]["max_spike_velocity"]
    f_max = results["final"]["max_spike_velocity"]
    if r:
        print(f"  total spike count:  {r} → {d} ({(d-r)/r*100:+.1f}%) → {f} ({(f-r)/r*100:+.1f}%)")
    if r_max:
        print(f"  max |Δ| velocity:   {r_max:.4f} → {d_max:.4f} ({(d_max-r_max)/r_max*100:+.1f}%) → {f_max:.4f} ({(f_max-r_max)/r_max*100:+.1f}%)")

    # 의심 프레임 PNG 추출 (raw 기준 상위).
    out_dir = here / "spike_frames"
    out_dir.mkdir(exist_ok=True)
    seen_frames: set[int] = set()
    print(f"\n=== Top spike frames (saving PNGs to {out_dir.name}/) ===")
    print(f"{'frame':>6} {'landmark':<28} {'raw |Δ|':>10} {'despiked |Δ|':>14}")
    for frame_idx, col, vel in results["raw"]["spike_frames"][:30]:
        if frame_idx in seen_frames:
            continue
        seen_frames.add(frame_idx)
        # 같은 (frame, col) 의 despiked 변화량 비교.
        arr = despiked[col].to_numpy(dtype=float)
        if 0 < frame_idx < len(arr):
            d_vel = abs(arr[frame_idx] - arr[frame_idx - 1])
        else:
            d_vel = float("nan")
        print(f"{frame_idx:>6d} {col:<28} {vel:>10.4f} {d_vel:>14.4f}")
        if len(seen_frames) <= TOP_K_FRAMES:
            png_path = out_dir / f"frame_{frame_idx:04d}.png"
            _save_frame_png(video, frame_idx, png_path)
        if len(seen_frames) >= TOP_K_FRAMES * 2:
            break
    return 0


if __name__ == "__main__":
    sys.exit(main())
