"""
Cadence 밴드 실측 검증 스크립트 (2026-05-29).

4영상 (pace530/6/630/7) 의 측정 cadence_spm 을 우리 4밴드 (170cm 기준) 와
비교한다. knee 임계 재조정 (2026-05-25) 과 동일 패턴.

가정:
- 영상 속 러너의 실제 신장은 미지 — 일단 170cm 기본으로 측정.
  (사용자 회신으로 실 신장 확인 후 보정 가능)
- pace 는 파일명에서 추정 (pace530 = 5:30/km = 330 sec/km).

산출:
- per-video: cadence_spm, expected (lo, hi), hint, deviation_pct
- 전 영상 요약 표 + 밴드 정합성 정성 평가
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parents[1]
ROOT = SERVER_DIR.parent
sys.path.insert(0, str(SERVER_DIR))

from analyzer import run_full_analysis  # noqa: E402


VIDEOS: dict[str, int] = {
    "pace530.mp4": 330,  # 5:30/km
    "pace6.mp4": 360,    # 6:00/km
    "pace630.mp4": 390,  # 6:30/km
    "pace7.mp4": 420,    # 7:00/km
}

HEIGHT_CM = 170.0  # 기본값 — 실 신장 확인 후 재실행 가능


def main() -> None:
    results = []
    total_start = time.time()
    for fn, pace_sec in VIDEOS.items():
        path = SERVER_DIR / fn
        if not path.exists():
            print(f"[SKIP] {fn} not found at {path}", flush=True)
            continue
        print(f"\n=== Analyzing {fn} (pace={pace_sec}s/km, height={HEIGHT_CM}cm) ===", flush=True)
        t0 = time.time()
        r = run_full_analysis(
            str(path),
            height_cm=HEIGHT_CM,
            pace_sec_per_km=float(pace_sec),
        )
        elapsed = time.time() - t0

        s = r.summary
        cadence = s.get("cadence_spm")
        lo = s.get("expected_cadence_min")
        hi = s.get("expected_cadence_max")
        hint = s.get("cadence_hint")
        dev = s.get("cadence_deviation_pct")
        n_strikes = s.get("strike_count_total") or s.get("strike_count_left", 0) + s.get("strike_count_right", 0)
        duration = s.get("duration_s") or s.get("video_duration_s")

        print(
            f"  cadence_spm={cadence}  expected=({lo}, {hi})  "
            f"hint={hint}  dev={dev}%  strikes={n_strikes}  duration={duration}s  "
            f"[analysis {elapsed:.1f}s]",
            flush=True,
        )
        results.append({
            "file": fn,
            "pace_sec_per_km": pace_sec,
            "cadence_spm": cadence,
            "expected_lo": lo,
            "expected_hi": hi,
            "hint": hint,
            "deviation_pct": dev,
            "strike_count": n_strikes,
            "duration_s": duration,
            "analysis_elapsed_s": round(elapsed, 1),
        })

    total = time.time() - total_start
    print(f"\n=== Total elapsed: {total:.1f}s ===\n", flush=True)
    print("=== Summary table ===", flush=True)
    print(f"{'file':<14}{'pace':<8}{'cadence':<10}{'expected':<14}{'hint':<10}{'dev%':<8}", flush=True)
    for x in results:
        exp = f"({x['expected_lo']},{x['expected_hi']})"
        print(
            f"{x['file']:<14}{x['pace_sec_per_km']:<8}{x['cadence_spm']:<10}"
            f"{exp:<14}{x['hint']:<10}{x['deviation_pct']:<8}",
            flush=True,
        )

    out_path = SERVER_DIR / "scripts" / "validate_cadence_bands_output.json"
    out_path.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nResults saved: {out_path}", flush=True)


if __name__ == "__main__":
    main()
