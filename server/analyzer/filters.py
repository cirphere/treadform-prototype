"""
시계열 신호 필터.

One Euro Filter:
    Casiez, Roussel & Vogel (2012). "1€ filter: a simple speed-based low-pass
    filter for noisy input in interactive systems."
    MediaPipe / Apple Vision / Plask 등 상용 실시간 pose 트래킹이 표준으로 사용.

핵심 아이디어:
    저역통과 cutoff 주파수를 신호 속도에 따라 적응시킨다.
        cutoff(t) = min_cutoff + beta * |dx/dt|
    - 정지/저속: 낮은 cutoff → 강한 평활화 (jitter 제거)
    - 고속 이동: 높은 cutoff → 약한 평활화 (lag 없음)
    EMA 의 고정 α 와 달리 같은 필터로 양 끝 사용 사례를 동시에 만족.
"""
from __future__ import annotations

import math

import numpy as np


def _alpha(cutoff: float, dt: float) -> float:
    """저역통과 1차 필터의 시간상수 → α (EMA 등가)."""
    tau = 1.0 / (2.0 * math.pi * cutoff)
    return 1.0 / (1.0 + tau / dt)


class OneEuroFilter:
    """
    스칼라 시계열용 One Euro Filter.

    파라미터:
        min_cutoff: 저속에서의 cutoff (Hz). 작을수록 강한 평활화.
        beta: 속도 적응 계수. 클수록 빠른 동작에 더 민감 (lag 감소).
        d_cutoff: 도함수 추정용 별도 cutoff (Hz).

    추천값 (mediapipe pose 30fps 측면 영상 기준):
        min_cutoff=1.0, beta=0.05  → 정적 부위(머리/몸통) 매우 부드러움
        min_cutoff=2.0, beta=0.10  → 사지(팔/다리) 균형
        min_cutoff=4.0, beta=0.30  → 발/손 (빠른 동작, 낮은 lag)
    """

    def __init__(
        self,
        min_cutoff: float = 1.0,
        beta: float = 0.05,
        d_cutoff: float = 1.0,
    ) -> None:
        self.min_cutoff = float(min_cutoff)
        self.beta = float(beta)
        self.d_cutoff = float(d_cutoff)
        self._x_prev: float | None = None
        self._dx_prev: float = 0.0

    def reset(self) -> None:
        self._x_prev = None
        self._dx_prev = 0.0

    def __call__(self, x: float, dt: float) -> float:
        if math.isnan(x):
            return float("nan")
        if self._x_prev is None or math.isnan(self._x_prev):
            self._x_prev = x
            self._dx_prev = 0.0
            return x

        # 1) 도함수 추정 + 평활화.
        dx = (x - self._x_prev) / dt
        a_d = _alpha(self.d_cutoff, dt)
        dx_hat = a_d * dx + (1.0 - a_d) * self._dx_prev

        # 2) 적응형 cutoff.
        cutoff = self.min_cutoff + self.beta * abs(dx_hat)

        # 3) 신호 평활화.
        a = _alpha(cutoff, dt)
        x_hat = a * x + (1.0 - a) * self._x_prev

        self._x_prev = x_hat
        self._dx_prev = dx_hat
        return x_hat


def one_euro_filter_array(
    series: np.ndarray,
    fps: float,
    min_cutoff: float = 2.0,
    beta: float = 0.10,
    d_cutoff: float = 1.0,
) -> np.ndarray:
    """
    1D 배열 전체에 OneEuroFilter 를 인과적으로 적용.

    NaN 은 그대로 두며, NaN 직후 첫 유효값은 재시드.
    """
    arr = np.asarray(series, dtype=float)
    n = arr.size
    out = np.full(n, np.nan, dtype=float)
    if n == 0:
        return out

    flt = OneEuroFilter(min_cutoff=min_cutoff, beta=beta, d_cutoff=d_cutoff)
    dt = 1.0 / fps if fps > 0 else 1.0 / 30.0

    for i in range(n):
        x = arr[i]
        if np.isnan(x):
            flt.reset()
            continue
        out[i] = flt(float(x), dt)
    return out


__all__ = ["OneEuroFilter", "one_euro_filter_array"]
