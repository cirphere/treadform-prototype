"""
PRD-7 분석 파이프라인 벤치마크.

기본 `pytest` 실행에선 자동 제외 (pytest.ini 의 addopts = -m "not benchmark").
명시적으로 다음과 같이 실행:

    venv\\Scripts\\python -m pytest tests\\test_benchmark.py -v -s -m benchmark

각 테스트는 end-to-end `run_full_analysis_with_output` 의 wall-clock 을 측정하고,
PRD-7 BENCHMARK.md 의 "영상 길이별" 표를 채울 데이터를 stdout 으로 출력한다.

샘플 영상 (server/pace*.mp4):
    pace530.mp4  8.5초 60fps 1920x1080
    pace7.mp4    11.1초 60fps 1920x1080
    pace630.mp4  16.2초 60fps 1920x1080
    pace6.mp4    22.9초 60fps 1920x1080
"""
from __future__ import annotations

import concurrent.futures
import shutil
import time
from pathlib import Path

import pytest

try:
    import psutil  # optional
except ImportError:
    psutil = None  # type: ignore[assignment]

ROOT = Path(__file__).resolve().parents[1]
BENCH_OUT = ROOT / "storage" / "benchmark"

SAMPLES = {
    "8s":  ROOT / "pace530.mp4",
    "11s": ROOT / "pace7.mp4",
    "16s": ROOT / "pace630.mp4",
    "23s": ROOT / "pace6.mp4",
}


def _require_sample(label: str) -> Path:
    p = SAMPLES[label]
    if not p.exists():
        pytest.skip(f"sample missing: {p}")
    return p


def _measure(video: Path, subdir: str) -> dict:
    """run_full_analysis_with_output 1회 측정."""
    from analyzer import run_full_analysis_with_output

    out_dir = BENCH_OUT / subdir
    if out_dir.exists():
        shutil.rmtree(out_dir, ignore_errors=True)
    out_dir.mkdir(parents=True, exist_ok=True)

    mem_before = psutil.virtual_memory().used if psutil else 0
    start = time.perf_counter()
    result = run_full_analysis_with_output(str(video), str(out_dir))
    elapsed = time.perf_counter() - start
    mem_after = psutil.virtual_memory().used if psutil else 0

    ar = result["analysis_result"]
    return {
        "video": video.name,
        "elapsed_sec": elapsed,
        "mem_delta_mb": (mem_after - mem_before) / (1024 * 1024) if psutil else None,
        "total_strikes": ar.summary["total_strikes"],
        "danger_count": ar.summary["danger_count"],
        "duration_sec": ar.summary["duration_sec"],
        "fps": ar.summary["fps"],
        "confidence": ar.confidence,
    }


def _print_row(m: dict) -> None:
    ratio = m["elapsed_sec"] / m["duration_sec"] if m["duration_sec"] else 0
    print(
        f"\n  {m['video']:14s} duration={m['duration_sec']:.1f}s "
        f"elapsed={m['elapsed_sec']:.2f}s ratio=1:{ratio:.2f} "
        f"strikes={m['total_strikes']} danger={m['danger_count']} "
        f"confidence={m['confidence']}"
        + (f" mem_delta={m['mem_delta_mb']:+.0f}MB" if m["mem_delta_mb"] is not None else "")
    )


@pytest.mark.benchmark
def test_analysis_speed_8s():
    """짧은 영상 (8.5초, 60fps 1080p)."""
    v = _require_sample("8s")
    m = _measure(v, "speed_8s")
    _print_row(m)
    assert m["elapsed_sec"] < 120, f"120s 한계 초과: {m['elapsed_sec']:.1f}s"


@pytest.mark.benchmark
def test_analysis_speed_11s():
    """실사용 시나리오 (11초, 60fps 1080p)."""
    v = _require_sample("11s")
    m = _measure(v, "speed_11s")
    _print_row(m)
    assert m["elapsed_sec"] < 150, f"150s 한계 초과: {m['elapsed_sec']:.1f}s"


@pytest.mark.benchmark
def test_analysis_speed_16s():
    """긴 영상 (16초, 60fps 1080p)."""
    v = _require_sample("16s")
    m = _measure(v, "speed_16s")
    _print_row(m)
    assert m["elapsed_sec"] < 240, f"240s 한계 초과: {m['elapsed_sec']:.1f}s"


@pytest.mark.benchmark
def test_concurrent_3_analyses():
    """3개 동시 요청 처리.

    동일한 영상 3개를 ThreadPoolExecutor 로 병렬 실행. mediapipe 가 GIL 을 풀고
    CPU 멀티코어를 활용하는지 + uvicorn 동시 처리 부하 시뮬레이션.
    """
    v = _require_sample("11s")

    def _job(i: int) -> dict:
        return _measure(v, f"concurrent_{i}")

    start = time.perf_counter()
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as exe:
        results = list(exe.map(_job, range(3)))
    total = time.perf_counter() - start

    individual = [r["elapsed_sec"] for r in results]
    print(
        f"\n  concurrent_3  total={total:.2f}s individual=[{', '.join(f'{x:.2f}' for x in individual)}]s"
        f" avg={sum(individual)/3:.2f}s"
    )
    # 3개 동시 처리가 단일 처리의 3배보다는 빨라야 (멀티코어 활용 확인).
    assert total < sum(individual) * 0.95, "병렬 처리 이득 없음"
