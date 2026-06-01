"""
한국어 AI 코칭 메시지 생성 (PRD-3).

AnalysisResult 의 status_counts / asymmetry 를 보고 우선순위 로직으로 가장
심각한 문제 2~3개를 골라 자연스러운 한국어 메시지를 합성한다.

Phase 1 (MVP) 은 템플릿 기반. 추후 LLM 호출 단계로 교체 가능하도록 함수 단위로
분리되어 있다.
"""
from __future__ import annotations

import logging

from config import ASYMMETRY_WARNING_THRESHOLD
from models.analysis_result import AnalysisResult

logger = logging.getLogger(__name__)


# 메시지 템플릿 ---------------------------------------------------------------

KNEE_MESSAGES: dict[str, str] = {
    "stiff_knee_dominant": (
        "무릎이 충분히 굽혀지지 않아 충격이 직접 전달되고 있습니다 ({count}회). "
        "착지 시 무릎이 살짝 더 굽혀지도록 의식해보세요."
    ),
    "over_bent_dominant": (
        "무릎이 과도하게 굽혀집니다 ({count}회). "
        "지나친 굴곡은 대퇴부 피로를 키울 수 있어 자세를 조금 더 편안하게 유지해보세요."
    ),
    "good_dominant": "무릎 굴곡 각도가 안정적으로 유지되고 있습니다 👍",
}

FOOT_STRIKE_MESSAGES: dict[str, str] = {
    "heel_dominant": (
        "뒤꿈치 착지가 {count}회로 다소 많이 발생했습니다. "
        "무릎 부담을 줄이려면 보폭을 조금 줄이고 중족 부위로 착지하는 연습을 추천드립니다."
    ),
    "midfoot_dominant": "중족 착지가 안정적으로 이루어지고 있습니다 👍",
    "forefoot_dominant": (
        "앞꿈치 착지 비율이 높습니다 ({count}회). 종아리 부담에 주의하세요."
    ),
}

OVERSTRIDE_MESSAGES: dict[str, str] = {
    "over_dominant": (
        "보폭이 과도하게 큽니다 ({count}회 오버스트라이딩 검출). "
        "케이던스를 약간 높이는 방향이 도움이 됩니다."
    ),
    "good": "보폭이 적절하게 유지되고 있습니다 👍",
}

VERTICAL_MESSAGES: dict[str, str] = {
    "high": (
        "상하 움직임이 크게 발생합니다. 에너지 낭비가 발생할 수 있으니 "
        "낮고 부드럽게 굴러가듯 달리는 느낌으로 조정해보세요."
    ),
    "high_cm": (
        "수직 진폭이 {value_cm:.1f}cm로 권장 상한({threshold_cm:.0f}cm)을 넘습니다. "
        "에너지 낭비가 발생할 수 있으니 낮고 부드럽게 굴러가듯 달리는 느낌으로 조정해보세요."
    ),
    "good": "수직 진폭이 효율적입니다 👍",
    "good_cm": "수직 진폭이 {value_cm:.1f}cm로 효율적인 범위에 있습니다 👍",
}

ASYMMETRY_MESSAGES: dict[str, str] = {
    "warning": (
        "좌우 비대칭({ratio:.0%})이 감지됩니다. "
        "편측 부상 가능성이 있어 약한 쪽 근력 강화를 권장드립니다."
    ),
}

# Phase 3 (2026-05-28): pace-aware cadence trailing info. 우선순위 issue 와
# 별개로 항상 메시지 끝에 1문장 첨부 (pace 입력 있을 때만).
CADENCE_MESSAGES: dict[str, str] = {
    "optimal": (
        "케이던스 {actual}spm 는 입력 페이스 기준 적정 범위({lo}-{hi})입니다 👍"
    ),
    "low": (
        "케이던스 {actual}spm 는 입력 페이스 기준 적정 범위({lo}-{hi})보다 "
        "{dev:.1f}% 낮습니다. 보폭을 약간 줄이고 빠른 회전으로 조정해보세요."
    ),
    "high": (
        "케이던스 {actual}spm 는 입력 페이스 기준 적정 범위({lo}-{hi})보다 "
        "{dev:.1f}% 높습니다. 보폭을 약간 늘려 호흡과 회전수를 균형 잡아보세요."
    ),
}

LOW_CONFIDENCE_PREFIX = (
    "※ 입력 영상 품질이 낮아 일부 분석이 부정확할 수 있습니다 (재촬영 권장).\n\n"
)


# 우선순위 판단 ---------------------------------------------------------------


def _foot_strike_total(result: AnalysisResult) -> int:
    fs = result.metrics.get("foot_strike", {}).get("status_counts", {})
    return int(fs.get("heel", 0) + fs.get("midfoot", 0) + fs.get("forefoot", 0))


def _knee_total(result: AnalysisResult) -> int:
    knee = result.metrics.get("knee_flexion", {}).get("status_counts", {})
    return int(knee.get("stiff", 0) + knee.get("good", 0)
               + knee.get("over_bent", 0) + knee.get("borderline", 0))


def _overstride_total(result: AnalysisResult) -> int:
    over = result.metrics.get("overstriding", {}).get("status_counts", {})
    return int(over.get("good", 0) + over.get("over", 0))


def select_priority_issues(result: AnalysisResult) -> list[str]:
    """
    심각한 문제부터 골라 카테고리 식별자 리스트를 반환.

    우선순위:
        1. asymmetry (편측 부상 위험)
        2. heel_strike 비율 ≥ 50%
        3. stiff_knee 또는 over_bent 비율 ≥ 30%
        4. over_stride 비율 ≥ 30%
        5. high vertical oscillation

    각 카테고리는 항상 존재하는지/없는지에 따라 별도 항목을 반환하므로
    호출자는 list 순서대로 메시지를 합성하면 된다.
    """
    issues: list[str] = []

    asym = result.asymmetry or {}
    if asym.get("is_warning"):
        issues.append("asymmetry")

    fs_counts = result.metrics.get("foot_strike", {}).get("status_counts", {})
    fs_total = _foot_strike_total(result)
    if fs_total > 0 and fs_counts.get("heel", 0) / fs_total >= 0.5:
        issues.append("foot_strike_heel")

    knee_counts = result.metrics.get("knee_flexion", {}).get("status_counts", {})
    knee_total = _knee_total(result)
    if knee_total > 0:
        stiff_ratio = knee_counts.get("stiff", 0) / knee_total
        overbent_ratio = knee_counts.get("over_bent", 0) / knee_total
        if stiff_ratio >= 0.3:
            issues.append("knee_stiff")
        elif overbent_ratio >= 0.3:
            issues.append("knee_overbent")

    over_counts = result.metrics.get("overstriding", {}).get("status_counts", {})
    over_total = _overstride_total(result)
    if over_total > 0 and over_counts.get("over", 0) / over_total >= 0.3:
        issues.append("overstride")

    if result.metrics.get("vertical_oscillation", {}).get("status") == "high":
        issues.append("vertical")

    return issues


# 메시지 생성 -----------------------------------------------------------------


def _asymmetry_ratio(result: AnalysisResult) -> float:
    asym = result.asymmetry or {}
    candidates = [
        asym.get("strike_count_ratio"),
        asym.get("knee_angle_ratio"),
        asym.get("oscillation_ratio"),
    ]
    finite = [r for r in candidates if isinstance(r, (int, float)) and r == r]
    return max(finite) if finite else ASYMMETRY_WARNING_THRESHOLD


def _render_issue(key: str, result: AnalysisResult) -> str:
    """카테고리 → 한 문장."""
    knee_counts = result.metrics.get("knee_flexion", {}).get("status_counts", {})
    fs_counts = result.metrics.get("foot_strike", {}).get("status_counts", {})
    over_counts = result.metrics.get("overstriding", {}).get("status_counts", {})

    if key == "asymmetry":
        return ASYMMETRY_MESSAGES["warning"].format(ratio=_asymmetry_ratio(result))
    if key == "foot_strike_heel":
        return FOOT_STRIKE_MESSAGES["heel_dominant"].format(
            count=fs_counts.get("heel", 0)
        )
    if key == "knee_stiff":
        return KNEE_MESSAGES["stiff_knee_dominant"].format(
            count=knee_counts.get("stiff", 0)
        )
    if key == "knee_overbent":
        return KNEE_MESSAGES["over_bent_dominant"].format(
            count=knee_counts.get("over_bent", 0)
        )
    if key == "overstride":
        return OVERSTRIDE_MESSAGES["over_dominant"].format(
            count=over_counts.get("over", 0)
        )
    if key == "vertical":
        vo = result.metrics.get("vertical_oscillation", {})
        value_cm = vo.get("avg_value_cm")
        threshold_cm = vo.get("threshold_cm")
        if value_cm is not None and threshold_cm is not None:
            return VERTICAL_MESSAGES["high_cm"].format(
                value_cm=value_cm, threshold_cm=threshold_cm,
            )
        return VERTICAL_MESSAGES["high"]
    return ""


def _all_good_message(result: AnalysisResult) -> str:
    """문제 없을 때의 칭찬 메시지."""
    parts = ["오늘 러닝 자세는 전반적으로 안정적입니다."]
    knee_counts = result.metrics.get("knee_flexion", {}).get("status_counts", {})
    fs_counts = result.metrics.get("foot_strike", {}).get("status_counts", {})
    over_status = result.metrics.get("overstriding", {}).get("status_counts", {})
    vert_status = result.metrics.get("vertical_oscillation", {}).get("status")

    if knee_counts.get("good", 0) > 0:
        parts.append(KNEE_MESSAGES["good_dominant"])
    if fs_counts.get("midfoot", 0) >= max(
        fs_counts.get("heel", 0), fs_counts.get("forefoot", 0)
    ):
        parts.append(FOOT_STRIKE_MESSAGES["midfoot_dominant"])
    if over_status.get("good", 0) > 0 and over_status.get("over", 0) == 0:
        parts.append(OVERSTRIDE_MESSAGES["good"])
    if vert_status == "good":
        vo = result.metrics.get("vertical_oscillation", {})
        value_cm = vo.get("avg_value_cm")
        if value_cm is not None:
            parts.append(VERTICAL_MESSAGES["good_cm"].format(value_cm=value_cm))
        else:
            parts.append(VERTICAL_MESSAGES["good"])

    return " ".join(parts)


def _cadence_trailing(result: AnalysisResult) -> str:
    """pace 입력 있을 때 cadence info 1문장. pace 미입력 시 빈 문자열."""
    s = result.summary or {}
    if "expected_cadence_min" not in s or "cadence_hint" not in s:
        return ""
    hint = s["cadence_hint"]
    template = CADENCE_MESSAGES.get(hint)
    if template is None:
        return ""
    return template.format(
        actual=int(round(s.get("cadence_spm", 0))),
        lo=int(s["expected_cadence_min"]),
        hi=int(s["expected_cadence_max"]),
        dev=float(s.get("cadence_deviation_pct", 0.0)),
    )


def generate_korean_coach_message(result: AnalysisResult, max_issues: int = 3) -> str:
    """
    AnalysisResult → 한국어 코칭 메시지 (자연어 한 단락).

    Args:
        result: 분석 결과.
        max_issues: 합성에 포함할 최대 문제 개수 (기본 3).

    Returns:
        한국어 메시지 문자열. low confidence 면 머리말에 재촬영 권장 prefix.
        pace 입력이 있으면 끝에 cadence info 1문장 trailing append.
    """
    prefix = ""
    if result.confidence == "low":
        prefix = LOW_CONFIDENCE_PREFIX

    cadence_tail = _cadence_trailing(result)

    issues = select_priority_issues(result)[:max_issues]
    if not issues:
        body = _all_good_message(result)
    else:
        summary_intro = f"오늘 러닝에서 점검할 부분 {len(issues)}가지를 확인했습니다."
        sentences = [summary_intro] + [_render_issue(k, result) for k in issues]
        body = " ".join(s for s in sentences if s)

    parts = [prefix + body]
    if cadence_tail:
        parts.append(cadence_tail)
    msg = " ".join(parts)
    logger.info(
        "coach message generated: issues=%s, cadence_tail=%s, %d chars",
        issues, bool(cadence_tail), len(msg),
    )
    return msg


__all__ = [
    "KNEE_MESSAGES",
    "FOOT_STRIKE_MESSAGES",
    "OVERSTRIDE_MESSAGES",
    "VERTICAL_MESSAGES",
    "ASYMMETRY_MESSAGES",
    "CADENCE_MESSAGES",
    "select_priority_issues",
    "generate_korean_coach_message",
]
