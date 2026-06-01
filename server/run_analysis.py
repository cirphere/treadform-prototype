"""
End-to-end 분석 실행 스크립트.

사용:
    python run_analysis.py [video_path]
기본 경로: server/running_video.mp4
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

from analyzer import run_full_analysis


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    here = Path(__file__).parent
    video = Path(sys.argv[1]) if len(sys.argv) > 1 else here / "running_video.mp4"
    if not video.exists():
        print(f"[ERROR] video not found: {video}")
        return 1

    print(f"[INFO] analyzing: {video}")
    result = run_full_analysis(str(video))

    payload = result.model_dump()

    # 요약 출력.
    print("\n=== SUMMARY ===")
    print(json.dumps(payload["summary"], indent=2, ensure_ascii=False))

    print("\n=== KNEE FLEXION ===")
    knee = payload["metrics"]["knee_flexion"]
    print(
        json.dumps(
            {
                "avg_angle": knee["avg_angle"],
                "left_avg": knee["left_avg"],
                "right_avg": knee["right_avg"],
                "status_counts": knee["status_counts"],
            },
            indent=2,
            ensure_ascii=False,
        )
    )

    print("\n=== FOOT STRIKE ===")
    print(
        json.dumps(
            payload["metrics"]["foot_strike"]["status_counts"],
            indent=2,
            ensure_ascii=False,
        )
    )

    print("\n=== OVERSTRIDING ===")
    over = payload["metrics"]["overstriding"]
    print(
        json.dumps(
            {"avg_distance": over["avg_distance"], "status_counts": over["status_counts"]},
            indent=2,
            ensure_ascii=False,
        )
    )

    print("\n=== VERTICAL OSCILLATION ===")
    vosc = payload["metrics"]["vertical_oscillation"]
    print(
        json.dumps(
            {
                "avg_value": vosc["avg_value"],
                "left_avg": vosc["left_avg"],
                "right_avg": vosc["right_avg"],
                "status": vosc["status"],
            },
            indent=2,
            ensure_ascii=False,
        )
    )

    print("\n=== ASYMMETRY ===")
    print(json.dumps(payload["asymmetry"], indent=2, ensure_ascii=False))

    print(f"\n=== DANGER TIMESTAMPS ({len(payload['danger_timestamps'])}) ===")
    for d in payload["danger_timestamps"][:20]:
        print(f"  t={d['time_sec']:.2f}s  type={d['type']}")
    if len(payload["danger_timestamps"]) > 20:
        print(f"  ... and {len(payload['danger_timestamps']) - 20} more")

    # 전체 JSON 저장.
    out_path = here / "analysis_result.json"
    out_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )
    print(f"\n[INFO] full result saved: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
