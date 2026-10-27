"""RISK/SAFE/UNKNOWN 최종 분기 (SPEC 1.3.1, 2.10)

1. 추출 요소가 indicators에서 scam이면 바로 RISK/high (LLM 호출 전에 check_blacklist로 확인)
2. LLM 결과가 없거나(형식·API 오류) 추출이 불완전하면 UNKNOWN
3. RISK/high: 강한 신호 1개 이상, 신호 2개 이상, 규칙 기반 안전장치 일치,
   공식 정보로 확인되지 않은 URL·전화번호와 의심 근거(신호 또는 LLM 의심)의 결합
4. RISK/low(주의): 약한 신호 1개, 미확인 URL·전화번호만 있음, LLM 의심 판단만 있음
5. 나머지는 SAFE. 안전을 보장한다는 뜻이 아니라 위험 신호를 찾지 못했다는 뜻이다.

UNKNOWN은 판정을 끝내지 못한 경우에만 쓴다. 신호는 judge()가 근거 문구를 확인한 결과여야 한다.

라우터 사용 예:
    result = check_blacklist(entity_matches)
    if result is None:
        judgement = await judge_async(...)   # scam이 없을 때만 LLM 호출
        result = decide(entity_matches, judgement, matched_cases, extracted=extracted, message=message)
"""

from dataclasses import dataclass
from enum import Enum
from typing import Any, Literal
from urllib.parse import urlsplit

from pydantic import BaseModel

from app.services.extractor import ExtractedEntities
from app.services.llm_judge import STRONG_SIGNALS, LLMJudgement
from app.services.rule_guard import match_rules

# 신호가 이 개수 이상이면 약한 신호만으로도 RISK/high다
HIGH_RISK_MIN_SIGNALS = 2

TYPE_LABELS = {"url": "URL", "phone": "전화번호", "domain": "도메인"}

SAFE_REASON = "위험 신호가 발견되지 않았습니다"
UNKNOWN_REASON = "판별 중 오류가 발생해 판단을 보류했습니다"
UNCONFIRMED_REASON = "공식 확인되지 않은 링크·번호 포함"
SUSPICIOUS_REASON = "의심스러운 표현이 있습니다"


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
    guide_type: Literal["damage_stage", "prevention", "verification"]
    register_as_pending: bool = False


def _enum_str(v: Any) -> str:
    # ORM 객체의 label/type이 Enum이어도 "scam" 같은 문자열로 비교되게 한다
    return str(getattr(v, "value", v))


def _risk(
    reasons: list[str], matched_cases: int, *, register_as_pending: bool, high: bool = True
) -> DecisionResult:
    return DecisionResult(
        status=Status.RISK,
        risk_level="high" if high else "low",
        reasons=list(dict.fromkeys(reasons)),
        matched_cases=matched_cases,
        guide_type="damage_stage" if high else "verification",
        register_as_pending=register_as_pending,
    )


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
    return _risk(reasons, matched_cases, register_as_pending=False)


def _has_unconfirmed_element(extracted: ExtractedEntities, entity_matches: list[EntityMatch]) -> bool:
    """공식 정보로 확인되지 않은 URL·전화번호가 있으면 True.

    URL은 호스트가 공식 도메인과 완전 일치하고 기본 포트일 때만 확인된 것으로 본다(SPEC 2.10).
    경로·쿼리는 확인 여부를 바꾸지 않으며 LLM이 위험 신호로 평가한다.
    """
    official = {
        (_enum_str(m.type), m.value) for m in entity_matches if _enum_str(m.label) == "official"
    }
    official_domains = {value for kind, value in official if kind == "domain"}
    for url in extracted.urls:
        parts = urlsplit(url)
        if parts.port is not None or parts.hostname not in official_domains:
            return True
    for domain in extracted.domains:
        if domain not in official_domains:
            return True
    return any(("phone", phone) not in official for phone in extracted.phones)


def decide(
    entity_matches: list[EntityMatch],
    judgement: LLMJudgement | None,
    matched_cases: int = 0,
    *,
    extracted: ExtractedEntities,
    message: str,
) -> DecisionResult:
    blacklisted = check_blacklist(entity_matches, matched_cases)
    if blacklisted:
        return blacklisted

    if judgement is None or extracted.unparsed_urls:
        return DecisionResult(
            status=Status.UNKNOWN,
            risk_level="unknown",
            reasons=[UNKNOWN_REASON],
            matched_cases=matched_cases,
            guide_type="verification",
        )

    signals = [s.signal for s in judgement.signals]
    suspected = bool(signals) or judgement.suspicious
    rules = match_rules(message)
    unconfirmed = _has_unconfirmed_element(extracted, entity_matches)

    reasons: list[str] = []
    if suspected:
        reasons += judgement.reasons or signals or [SUSPICIOUS_REASON]
    reasons += [f"{rule} 의심 표현 포함" for rule in rules]
    if unconfirmed:
        reasons.append(UNCONFIRMED_REASON)
    if reasons:
        high = (
            any(signal in STRONG_SIGNALS for signal in signals)
            or len(signals) >= HIGH_RISK_MIN_SIGNALS
            or bool(rules)
            or (unconfirmed and suspected)
        )
        return _risk(reasons, matched_cases, register_as_pending=True, high=high)

    return DecisionResult(
        status=Status.SAFE,
        risk_level="low",
        reasons=[SAFE_REASON],
        matched_cases=matched_cases,
        guide_type="prevention",
    )
