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
    "good": "수직 진폭이 효율적입니다 👍",
}

POSTURE_MESSAGES: dict[str, str] = {
    "landing_tibia": (
        "착지 순간 정강이 기울기가 큰 구간이 {count}회 감지됐습니다. "
        "발을 몸 아래에 더 가깝게 내려놓는 느낌으로 보폭을 조절해보세요."
    ),
    "torso_too_upright": (
        "몸통이 거의 세워진 상태로 달리는 경향이 있습니다. "
        "발목부터 몸 전체가 아주 살짝 앞으로 기울어진 느낌을 만들어보세요."
    ),
    "torso_excessive": (
        "몸통 기울기가 과하게 큽니다. 허리만 접기보다 시선과 가슴을 편하게 유지해보세요."
    ),
    "arm_tight": "팔꿈치가 너무 접혀 상체 긴장이 커질 수 있습니다. 팔을 조금 더 편하게 흔들어보세요.",
    "arm_open": "팔이 과하게 펴져 리듬이 흐트러질 수 있습니다. 팔꿈치를 자연스럽게 접어보세요.",
    "head_forward": "머리가 어깨보다 앞으로 빠지는 경향이 있습니다. 시선은 전방, 목은 길게 유지해보세요.",
}

ASYMMETRY_MESSAGES: dict[str, str] = {
    "warning": (
        "좌우 비대칭({ratio:.0%})이 감지됩니다. "
        "편측 부상 가능성이 있어 약한 쪽 근력 강화를 권장드립니다."
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


def _landing_tibia_total(result: AnalysisResult) -> int:
    tibia = result.metrics.get("landing_tibia", {}).get("status_counts", {})
    return int(tibia.get("good", 0) + tibia.get("overreach", 0) + tibia.get("unknown", 0))


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

    tibia_counts = result.metrics.get("landing_tibia", {}).get("status_counts", {})
    tibia_total = _landing_tibia_total(result)
    if tibia_total > 0 and tibia_counts.get("overreach", 0) / tibia_total >= 0.3:
        issues.append("landing_tibia")

    torso_status = result.metrics.get("torso_posture", {}).get("status")
    if torso_status == "too_upright":
        issues.append("torso_too_upright")
    elif torso_status == "excessive_lean":
        issues.append("torso_excessive")

    arm_status = result.metrics.get("arm_position", {}).get("status")
    if arm_status == "too_tight":
        issues.append("arm_tight")
    elif arm_status == "too_open":
        issues.append("arm_open")

    if result.metrics.get("head_position", {}).get("status") == "forward_head":
        issues.append("head_forward")

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
    tibia_counts = result.metrics.get("landing_tibia", {}).get("status_counts", {})

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
        return VERTICAL_MESSAGES["high"]
    if key == "landing_tibia":
        return POSTURE_MESSAGES["landing_tibia"].format(
            count=tibia_counts.get("overreach", 0)
        )
    if key in POSTURE_MESSAGES:
        return POSTURE_MESSAGES[key]
    return ""


def _all_good_message(result: AnalysisResult) -> str:
    """문제 없을 때의 칭찬 메시지."""
    parts = ["오늘 러닝 자세는 전반적으로 안정적입니다."]
    knee_counts = result.metrics.get("knee_flexion", {}).get("status_counts", {})
    fs_counts = result.metrics.get("foot_strike", {}).get("status_counts", {})
    over_status = result.metrics.get("overstriding", {}).get("status_counts", {})
    vert_status = result.metrics.get("vertical_oscillation", {}).get("status")
    torso_status = result.metrics.get("torso_posture", {}).get("status")
    arm_status = result.metrics.get("arm_position", {}).get("status")
    head_status = result.metrics.get("head_position", {}).get("status")

    if knee_counts.get("good", 0) > 0:
        parts.append(KNEE_MESSAGES["good_dominant"])
    if fs_counts.get("midfoot", 0) >= max(
        fs_counts.get("heel", 0), fs_counts.get("forefoot", 0)
    ):
        parts.append(FOOT_STRIKE_MESSAGES["midfoot_dominant"])
    if over_status.get("good", 0) > 0 and over_status.get("over", 0) == 0:
        parts.append(OVERSTRIDE_MESSAGES["good"])
    if vert_status == "good":
        parts.append(VERTICAL_MESSAGES["good"])
    if torso_status == "neutral_torso":
        parts.append("몸통 자세가 안정적으로 유지되고 있습니다.")
    if arm_status == "good_arm_swing":
        parts.append("팔 스윙 리듬도 자연스럽습니다.")
    if head_status == "aligned_head":
        parts.append("머리와 어깨 정렬이 좋습니다.")

    return " ".join(parts)


def generate_korean_coach_message(result: AnalysisResult, max_issues: int = 3) -> str:
    """
    AnalysisResult → 한국어 코칭 메시지 (자연어 한 단락).

    Args:
        result: 분석 결과.
        max_issues: 합성에 포함할 최대 문제 개수 (기본 3).

    Returns:
        한국어 메시지 문자열. low confidence 면 머리말에 재촬영 권장 prefix.
    """
    prefix = ""
    if result.confidence == "low":
        prefix = LOW_CONFIDENCE_PREFIX

    issues = select_priority_issues(result)[:max_issues]
    if not issues:
        msg = prefix + _all_good_message(result)
        logger.info("coach message generated (all good): %d chars", len(msg))
        return msg

    summary_intro = f"오늘 러닝에서 점검할 부분 {len(issues)}가지를 확인했습니다."
    sentences = [summary_intro] + [_render_issue(k, result) for k in issues]
    msg = prefix + " ".join(s for s in sentences if s)
    logger.info("coach message generated: issues=%s, %d chars", issues, len(msg))
    return msg


__all__ = [
    "KNEE_MESSAGES",
    "FOOT_STRIKE_MESSAGES",
    "OVERSTRIDE_MESSAGES",
    "VERTICAL_MESSAGES",
    "ASYMMETRY_MESSAGES",
    "select_priority_issues",
    "generate_korean_coach_message",
]
