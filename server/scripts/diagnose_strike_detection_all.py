"""
4영상 strike detection cooldown sweep (2026-05-29).

ground truth (사용자 수동 카운트):
    pace530: 25
    pace6:   66~68
    pace630: (미확인)
    pace7:   (미확인)

목표:
- 4영상 모두 동일 cooldown 으로 GT 또는 plateau 에 수렴하는지 확인
- FOOT_STRIKE_COOLDOWN_FRAMES default 변경의 일반성 검증
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

SERVER_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVER_DIR))

from analyzer.foot_strike_detector import detect_foot_strikes  # noqa: E402
from analyzer.pose_extractor import extract_pose_series  # noqa: E402
from analyzer.preprocessor import preprocess_pose_dataframe  # noqa: E402


VIDEOS = {
    "pace530.mp4": 25,
    "pace6.mp4":   67,   # 66~68 의 중앙값
    "pace630.mp4": 45,
    "pace7.mp4":   33,
}

COOLDOWNS = (5, 10, 15, 20, 25, 30, 35, 40, 45, 50)


def analyze_video(name: str, gt: int | None) -> dict:
    path = SERVER_DIR / name
    print(f"\n=== {name} (GT={gt if gt is not None else '?'}) ===", flush=True)
    raw = extract_pose_series(str(path))
    df = preprocess_pose_dataframe(raw)
    fps = float(df.attrs.get("fps", 60.0))
    duration = len(df) / fps
    print(f"  frames={len(df)} fps={fps:.2f} duration={duration:.2f}s", flush=True)

    left_y = df["left_ankle_y"].to_numpy(dtype=float)
    right_y = df["right_ankle_y"].to_numpy(dtype=float)

    sweep = {}
    header = f"  {'cd':<5}{'L':<5}{'R':<5}{'tot':<6}"
    if gt is not None:
        header += f"{'vs_GT':<8}{'spm':<8}"
    else:
        header += f"{'spm':<8}"
    print(header, flush=True)

    for cd in COOLDOWNS:
        l = len(detect_foot_strikes(left_y, cooldown=cd))
        r = len(detect_foot_strikes(right_y, cooldown=cd))
        tot = l + r
        spm = tot / duration * 60.0 if duration > 0 else 0.0
        sweep[cd] = (l, r, tot, spm)
        row = f"  {cd:<5}{l:<5}{r:<5}{tot:<6}"
        if gt is not None:
            diff = tot - gt
            row += f"{'+' if diff > 0 else '':<1}{diff:<7}{spm:<8.1f}"
        else:
            row += f"{spm:<8.1f}"
        print(row, flush=True)

    return {"name": name, "gt": gt, "fps": fps, "duration": duration, "sweep": sweep}


def main() -> None:
    results = []
    for name, gt in VIDEOS.items():
        results.append(analyze_video(name, gt))

    print("\n\n=== Summary: total strikes by cooldown ===", flush=True)
    header = f"{'cooldown':<10}" + "".join(f"{r['name']:<13}" for r in results)
    print(header, flush=True)
    gt_row = f"{'GT':<10}" + "".join(f"{(str(r['gt']) if r['gt'] else '?'):<13}" for r in results)
    print(gt_row, flush=True)
    for cd in COOLDOWNS:
        row = f"{cd:<10}"
        for r in results:
            l, rr, tot, spm = r["sweep"][cd]
            row += f"{f'{tot} ({spm:.0f})':<13}"
        print(row, flush=True)


if __name__ == "__main__":
    main()
