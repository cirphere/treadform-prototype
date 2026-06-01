"""
PRD-3 coach_message 단위 테스트.

템플릿 분기와 우선순위 로직을 합성 AnalysisResult 로 검증한다.
"""
from __future__ import annotations

import pytest

from analyzer.coach_message import (
    FOOT_STRIKE_MESSAGES,
    KNEE_MESSAGES,
    LOW_CONFIDENCE_PREFIX,
    OVERSTRIDE_MESSAGES,
    VERTICAL_MESSAGES,
    generate_korean_coach_message,
    select_priority_issues,
)
from models.analysis_result import AnalysisResult


def _build_result(
    *,
    knee_counts: dict | None = None,
    fs_counts: dict | None = None,
    over_counts: dict | None = None,
    vertical_status: str = "good",
    asymmetry: dict | None = None,
    confidence: str = "high",
    knee_per_strike: list | None = None,
    fs_per_strike: list | None = None,
    over_per_strike: list | None = None,
    vert_per_stride: list | None = None,
) -> AnalysisResult:
    return AnalysisResult(
        analysis_id="test",
        summary={
            "total_frames": 100,
            "duration_sec": 10.0,
            "fps": 30.0,
            "total_strikes": 10,
            "left_strikes": 5,
            "right_strikes": 5,
            "danger_count": 0,
            "cadence_spm": 0.0,
        },
        metrics={
            "knee_flexion": {
                "avg_angle": 150.0,
                "left_avg": 150.0,
                "right_avg": 150.0,
                "status_counts": knee_counts
                or {"stiff": 0, "good": 10, "over_bent": 0, "borderline": 0},
                "per_strike": knee_per_strike or [],
            },
            "foot_strike": {
                "status_counts": fs_counts
                or {"heel": 0, "midfoot": 10, "forefoot": 0},
                "per_strike": fs_per_strike or [],
            },
            "overstriding": {
                "avg_distance": 0.1,
                "status_counts": over_counts or {"good": 10, "over": 0},
                "per_strike": over_per_strike or [],
            },
            "vertical_oscillation": {
                "avg_value": 0.05,
                "left_avg": 0.05,
                "right_avg": 0.05,
                "status": vertical_status,
                "per_stride": vert_per_stride or [],
            },
        },
        asymmetry=asymmetry
        or {
            "strike_count_ratio": 0.0,
            "knee_angle_ratio": 0.0,
            "oscillation_ratio": 0.0,
            "is_warning": False,
        },
        confidence=confidence,
    )


# ---------------------------------------------------------------------------
# select_priority_issues
# ---------------------------------------------------------------------------


def test_priority_asymmetry_first():
    r = _build_result(
        asymmetry={
            "strike_count_ratio": 0.3,
            "knee_angle_ratio": 0.1,
            "oscillation_ratio": 0.0,
            "is_warning": True,
        },
        fs_counts={"heel": 8, "midfoot": 2, "forefoot": 0},
    )
    issues = select_priority_issues(r)
    assert issues[0] == "asymmetry"
    assert "foot_strike_heel" in issues


def test_priority_heel_strike_threshold():
    r = _build_result(fs_counts={"heel": 5, "midfoot": 5, "forefoot": 0})
    assert "foot_strike_heel" in select_priority_issues(r)

    r2 = _build_result(fs_counts={"heel": 4, "midfoot": 6, "forefoot": 0})
    assert "foot_strike_heel" not in select_priority_issues(r2)


def test_priority_empty_when_all_good():
    r = _build_result()
    assert select_priority_issues(r) == []


# ---------------------------------------------------------------------------
# generate_korean_coach_message
# ---------------------------------------------------------------------------


def test_message_heel_dominant():
    r = _build_result(fs_counts={"heel": 8, "midfoot": 2, "forefoot": 0})
    msg = generate_korean_coach_message(r)
    assert "뒤꿈치 착지" in msg
    assert "8회" in msg


def test_message_all_good_includes_positive_token():
    r = _build_result()
    msg = generate_korean_coach_message(r)
    assert "안정적" in msg or "👍" in msg
    assert "오늘 러닝" in msg


def test_message_asymmetry_warning_appears():
    r = _build_result(
        asymmetry={
            "strike_count_ratio": 0.2,
            "knee_angle_ratio": 0.05,
            "oscillation_ratio": 0.0,
            "is_warning": True,
        }
    )
    msg = generate_korean_coach_message(r)
    assert "비대칭" in msg
    assert "20%" in msg  # max ratio 가 0.2 → 20%


def test_message_low_confidence_prefix():
    r = _build_result(confidence="low")
    msg = generate_korean_coach_message(r)
    assert msg.startswith(LOW_CONFIDENCE_PREFIX)


def test_message_knee_stiff_dominant():
    r = _build_result(
        knee_counts={"stiff": 5, "good": 3, "over_bent": 0, "borderline": 2}
    )
    msg = generate_korean_coach_message(r)
    assert "무릎" in msg
    assert "5회" in msg


def test_message_overstride_dominant():
    r = _build_result(over_counts={"good": 5, "over": 5})
    msg = generate_korean_coach_message(r)
    assert "보폭" in msg or "오버스트라이딩" in msg


def test_message_vertical_high():
    r = _build_result(vertical_status="high")
    msg = generate_korean_coach_message(r)
    assert "상하" in msg or "수직" in msg or "낮고" in msg


def test_message_max_issues_truncation():
    """max_issues=2 면 최대 2개 카테고리만 포함."""
    r = _build_result(
        knee_counts={"stiff": 5, "good": 3, "over_bent": 0, "borderline": 2},
        fs_counts={"heel": 8, "midfoot": 2, "forefoot": 0},
        over_counts={"good": 5, "over": 5},
        vertical_status="high",
        asymmetry={
            "strike_count_ratio": 0.3,
            "knee_angle_ratio": 0.0,
            "oscillation_ratio": 0.0,
            "is_warning": True,
        },
    )
    msg = generate_korean_coach_message(r, max_issues=2)
    assert "2가지" in msg


def test_message_natural_no_format_braces():
    """템플릿 placeholder ({count}, {ratio}) 가 그대로 노출되면 안 됨."""
    for status in ("stiff", "over_bent", "good"):
        counts = {"stiff": 0, "good": 0, "over_bent": 0, "borderline": 0}
        counts[status] = 5
        r = _build_result(knee_counts=counts)
        msg = generate_korean_coach_message(r)
        assert "{" not in msg and "}" not in msg


# ---------------------------------------------------------------------------
# 템플릿 자체 sanity
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "templates",
    [KNEE_MESSAGES, FOOT_STRIKE_MESSAGES, OVERSTRIDE_MESSAGES, VERTICAL_MESSAGES],
)
def test_template_has_korean(templates):
    """모든 템플릿 메시지에 한글이 포함되어야 함."""
    for msg in templates.values():
        assert any("가" <= ch <= "힣" for ch in msg)
