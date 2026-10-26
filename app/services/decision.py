"""RISK/SAFE/UNKNOWN 최종 분기

1. 추출 요소가 entities에서 scam이면 바로 RISK (LLM 호출 전에 check_blacklist로 확인)
2. LLM 결과가 없으면(형식·API 오류) UNKNOWN
3. LLM이 고위험 신호 조합을 판단하면 RISK, 문구는 cases에 pending 등록 대상
4. official 일치 + LLM 위험 신호 없음이면 SAFE
5. 그 외 전부 UNKNOWN

라우터 사용 예:
    result = check_blacklist(entity_matches)
    if result is None:
        judgement = await llm_judge(...)   # scam이 없을 때만 LLM 호출
        result = decide(entity_matches, judgement, matched_cases)
"""

from dataclasses import dataclass
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel

from app.services.llm_judge import LLMJudgement

# "고위험 신호 조합"으로 인정할 최소 신호 개수
HIGH_RISK_MIN_SIGNALS = 2

TYPE_LABELS = {"url": "URL", "phone": "전화번호", "domain": "도메인"}


class Status(str, Enum):
    RISK = "RISK"
    SAFE = "SAFE"
    UNKNOWN = "UNKNOWN"


@dataclass
class EntityMatch:
    value: str
    type: Literal["url", "phone", "domain"]
    label: Literal["scam", "official"]


class DecisionResult(BaseModel):
    status: Status
    risk_level: Literal["high", "low", "unknown"]
    reasons: list[str] = []
    matched_cases: int = 0
    guide_type: Literal["damage_stage", "verify_first", "none"]
    register_as_pending: bool = False


def _enum_str(v: Any) -> str:
    # ORM 객체의 label/type이 Enum이어도 "scam" 같은 문자열로 비교되게 한다
    return str(getattr(v, "value", v))


def check_blacklist(
    entity_matches: list[EntityMatch],
    matched_cases: int = 0,
) -> DecisionResult | None:
    """1번 분기. scam이 있으면 RISK, 없으면 None (→ LLM 판단으로 진행)."""
    scam = [m for m in entity_matches if _enum_str(m.label) == "scam"]
    if not scam:
        return None

    # 악성 URL·번호 원문은 화면에 노출하지 않고 종류만 표시
    reasons = [f"신고된 피싱 {TYPE_LABELS.get(_enum_str(m.type), '요소')} 포함" for m in scam]
    return DecisionResult(
        status=Status.RISK,
        risk_level="high",
        reasons=list(dict.fromkeys(reasons)),
        matched_cases=matched_cases,
        guide_type="damage_stage",
    )


def decide(
    entity_matches: list[EntityMatch],
    judgement: LLMJudgement | None,
    matched_cases: int = 0,
) -> DecisionResult:
    blacklisted = check_blacklist(entity_matches, matched_cases)
    if blacklisted:
        return blacklisted

    if judgement is None:
        return DecisionResult(
            status=Status.UNKNOWN,
            risk_level="unknown",
            reasons=["판별 중 오류가 발생해 판단을 보류했습니다"],
            matched_cases=matched_cases,
            guide_type="verify_first",
        )

    if judgement.is_high_risk and len(judgement.signals) >= HIGH_RISK_MIN_SIGNALS:
        return DecisionResult(
            status=Status.RISK,
            risk_level="high",
            reasons=judgement.reasons or ["여러 위험 신호가 함께 발견되었습니다"],
            matched_cases=matched_cases,
            guide_type="damage_stage",
            register_as_pending=True,
        )

    has_official = any(_enum_str(m.label) == "official" for m in entity_matches)
    if has_official and not judgement.is_high_risk and not judgement.signals:
        return DecisionResult(
            status=Status.SAFE,
            risk_level="low",
            reasons=judgement.reasons or ["공식 등록된 번호·도메인과 일치합니다"],
            matched_cases=matched_cases,
            guide_type="none",
        )

    return DecisionResult(
        status=Status.UNKNOWN,
        risk_level="unknown",
        reasons=judgement.reasons or ["판단 근거가 부족합니다"],
        matched_cases=matched_cases,
        guide_type="verify_first",
    )