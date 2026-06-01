"""
preprocessor 단위 테스트.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from analyzer.filters import OneEuroFilter, one_euro_filter_array
from analyzer.preprocessor import (
    correct_lr_swaps,
    despike_pose_dataframe,
    exponential_moving_average,
    forward_fill_with_limit,
    hampel_filter,
    mask_low_visibility,
    preprocess_pose_dataframe,
)
from config import VISIBILITY_THRESHOLD


class TestForwardFill:
    def test_fill_within_limit(self):
        arr = np.array([1.0, np.nan, np.nan, 4.0])
        out = forward_fill_with_limit(arr, max_frames=2)
        assert out.tolist() == [1.0, 1.0, 1.0, 4.0]

    def test_exceeds_limit_keeps_nan(self):
        arr = np.array([1.0] + [np.nan] * 5 + [10.0])
        out = forward_fill_with_limit(arr, max_frames=3)
        # 처음 3개는 채워지고 나머지 2개는 NaN.
        assert out[1] == 1.0 and out[2] == 1.0 and out[3] == 1.0
        assert np.isnan(out[4]) and np.isnan(out[5])
        assert out[6] == 10.0

    def test_leading_nan_unchanged(self):
        arr = np.array([np.nan, np.nan, 5.0])
        out = forward_fill_with_limit(arr)
        assert np.isnan(out[0]) and np.isnan(out[1])
        assert out[2] == 5.0


class TestEMA:
    def test_first_valid_is_seed(self):
        out = exponential_moving_average(np.array([5.0]), alpha=0.3)
        assert out[0] == 5.0

    def test_smoothing_formula(self):
        # y_1 = α*x_1 + (1-α)*y_0 = 0.3*10 + 0.7*0 = 3.0
        out = exponential_moving_average(np.array([0.0, 10.0]), alpha=0.3)
        assert out[1] == pytest.approx(3.0)

    def test_reduces_variance(self):
        rng = np.random.default_rng(0)
        x = rng.normal(0, 1, 1000)
        y = exponential_moving_average(x, alpha=0.3)
        assert y.var() < x.var()


class TestHampelFilter:
    def test_passthrough_when_no_outlier(self):
        x = np.linspace(0.4, 0.5, 50)
        out = hampel_filter(x, window=5, k=3)
        np.testing.assert_allclose(out, x, atol=1e-12)

    def test_single_frame_spike_replaced(self):
        x = np.linspace(0.4, 0.5, 21).copy()
        x[10] = 0.95  # 명백한 spike
        out = hampel_filter(x, window=5, k=3)
        # 원래 위치에서 멀리 떨어진 spike 는 중앙값으로 회복.
        assert abs(out[10] - 0.45) < 0.01
        # 다른 인덱스는 그대로.
        for i in (0, 5, 15, 20):
            assert out[i] == pytest.approx(x[i])

    def test_preserves_sharp_peak_if_not_outlier(self):
        # 진짜 peak (착지 신호처럼) 은 보존되어야 함.
        # window 내 다른 값들이 어느 정도 비슷한 수준이면 outlier 가 아님.
        x = np.array([0.5, 0.55, 0.6, 0.7, 0.6, 0.55, 0.5])
        out = hampel_filter(x, window=5, k=3)
        # 정점 0.7 은 살짝 보정될 수도 있으나 0.6 이상 유지되어야.
        assert out[3] >= 0.6

    def test_nan_preserved(self):
        x = np.array([0.4, np.nan, 0.42, 0.43, 0.44])
        out = hampel_filter(x, window=5, k=3)
        assert np.isnan(out[1])

    def test_empty_series(self):
        out = hampel_filter(np.array([]))
        assert out.size == 0


class TestMaskLowVisibility:
    def _row(self, vis: float, x: float = 0.5) -> dict:
        return {
            "left_hip_x": x,
            "left_hip_y": x,
            "left_hip_z": 0.0,
            "left_hip_visibility": vis,
            "frame_idx": 0,
        }

    def test_below_threshold_masks_coords(self):
        df = pd.DataFrame([self._row(VISIBILITY_THRESHOLD - 0.05)])
        out = mask_low_visibility(df)
        assert np.isnan(out.at[0, "left_hip_x"])
        assert np.isnan(out.at[0, "left_hip_y"])
        # visibility 자체는 보존.
        assert out.at[0, "left_hip_visibility"] < VISIBILITY_THRESHOLD

    def test_above_threshold_unchanged(self):
        df = pd.DataFrame([self._row(VISIBILITY_THRESHOLD + 0.05, x=0.7)])
        out = mask_low_visibility(df)
        assert out.at[0, "left_hip_x"] == pytest.approx(0.7)


class TestOneEuroFilter:
    def test_passthrough_first_sample(self):
        flt = OneEuroFilter(min_cutoff=1.0, beta=0.05)
        assert flt(0.5, dt=1 / 30) == pytest.approx(0.5)

    def test_smooths_constant_signal(self):
        # 일정 값을 넣으면 정확히 그 값이 유지된다.
        flt = OneEuroFilter()
        outs = [flt(1.0, dt=1 / 30) for _ in range(20)]
        for o in outs:
            assert o == pytest.approx(1.0)

    def test_responsive_to_fast_motion(self):
        # 빠른 ramp 입력에서 적응형 cutoff 가 동작해 추적 가능.
        flt = OneEuroFilter(min_cutoff=1.0, beta=0.5)
        inputs = [0.0 + 0.1 * i for i in range(30)]
        outs = [flt(x, dt=1 / 30) for x in inputs]
        # 마지막 값에 충분히 가까이 따라잡았는지.
        assert outs[-1] > 2.0  # ramp 마지막은 2.9

    def test_reduces_jitter_when_static(self):
        rng = np.random.default_rng(0)
        n = 200
        noisy = rng.normal(0.5, 0.05, n)
        out = one_euro_filter_array(noisy, fps=30.0, min_cutoff=1.0, beta=0.05)
        assert out.std() < noisy.std() / 2

    def test_nan_resets_state(self):
        arr = np.array([0.5, 0.51, np.nan, 0.6])
        out = one_euro_filter_array(arr, fps=30.0)
        assert np.isnan(out[2])
        # NaN 이후 첫 유효값은 시드로 그대로.
        assert out[3] == pytest.approx(0.6)


class TestLRSwapCorrection:
    def _frame(self, idx: int, l_xy: tuple[float, float], r_xy: tuple[float, float]) -> dict:
        row = {"frame_idx": idx, "timestamp_sec": idx / 30.0}
        for j in ("hip", "knee", "ankle", "heel", "foot_index"):
            row[f"left_{j}_x"] = l_xy[0]
            row[f"left_{j}_y"] = l_xy[1]
            row[f"left_{j}_z"] = 0.0
            row[f"left_{j}_visibility"] = 1.0
            row[f"right_{j}_x"] = r_xy[0]
            row[f"right_{j}_y"] = r_xy[1]
            row[f"right_{j}_z"] = 0.0
            row[f"right_{j}_visibility"] = 1.0
        return row

    def test_no_swap_on_normal_motion(self):
        # 좌/우 발이 일관된 위치에서 작게 움직이는 정상 케이스.
        rows = []
        for i in range(20):
            rows.append(
                self._frame(i, l_xy=(0.4, 0.8 + 0.001 * i), r_xy=(0.6, 0.8 + 0.001 * i))
            )
        df = pd.DataFrame(rows)
        _, swaps = correct_lr_swaps(df)
        assert swaps == 0

    def test_detects_clear_swap(self):
        # 10프레임 정상, 11번째에서 좌/우가 명확히 뒤바뀜.
        rows = []
        for i in range(10):
            rows.append(self._frame(i, l_xy=(0.3, 0.8), r_xy=(0.7, 0.8)))
        # 다음 프레임에서 좌/우 swap (큰 거리 변화).
        rows.append(self._frame(10, l_xy=(0.7, 0.8), r_xy=(0.3, 0.8)))
        for i in range(11, 20):
            rows.append(self._frame(i, l_xy=(0.3, 0.8), r_xy=(0.7, 0.8)))
        df = pd.DataFrame(rows)
        corrected, swaps = correct_lr_swaps(df)
        assert swaps >= 1
        # 보정 후 좌측 X 는 0.3 근처로 회복.
        assert corrected.at[10, "left_hip_x"] == pytest.approx(0.3)
        assert corrected.at[10, "right_hip_x"] == pytest.approx(0.7)

    def test_handles_missing_lr_columns_gracefully(self):
        # 좌측만 있는 DataFrame (테스트 픽스처 등) 에서도 죽지 않음.
        df = pd.DataFrame(
            [{"frame_idx": 0, "left_hip_x": 0.5, "left_hip_y": 0.5}]
        )
        out, swaps = correct_lr_swaps(df)
        assert swaps == 0
        assert "left_hip_x" in out.columns


class TestPipelineOrder:
    def test_pipeline_includes_hampel_before_ema(self):
        # spike + 평활화가 함께 적용되는지 통합 확인.
        n = 30
        rows = []
        for i in range(n):
            rows.append(
                {
                    "frame_idx": i,
                    "timestamp_sec": i / 30.0,
                    "left_hip_x": 0.5,
                    "left_hip_y": 0.5,
                    "left_hip_z": 0.0,
                    "left_hip_visibility": 1.0,
                }
            )
        # 한 프레임만 큰 spike.
        rows[15]["left_hip_x"] = 0.95
        df = pd.DataFrame(rows)
        out = preprocess_pose_dataframe(df)
        # Hampel 이 작동했다면 EMA 후에도 0.95 영향이 거의 안 보여야.
        assert out.at[15, "left_hip_x"] < 0.6

    def test_despike_only_no_ema_lag(self):
        n = 20
        rows = []
        for i in range(n):
            rows.append(
                {
                    "frame_idx": i,
                    "timestamp_sec": i / 30.0,
                    "left_hip_x": 0.4 + 0.01 * i,
                    "left_hip_y": 0.5,
                    "left_hip_z": 0.0,
                    "left_hip_visibility": 1.0,
                }
            )
        rows[10]["left_hip_x"] = 0.95  # spike
        df = pd.DataFrame(rows)
        despiked = despike_pose_dataframe(df)
        # spike 는 제거되고 트렌드는 보존.
        assert despiked.at[10, "left_hip_x"] < 0.6
        # 양 끝은 lag 없이 원본과 거의 동일.
        assert despiked.at[0, "left_hip_x"] == pytest.approx(0.4)
        assert despiked.at[19, "left_hip_x"] == pytest.approx(0.4 + 0.01 * 19)
