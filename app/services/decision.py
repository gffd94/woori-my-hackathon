"""RISK/SAFE/UNKNOWN 최종 판정 (SPEC 1.3.1, 2.10)

판정 규칙은 decide_final 하나에 있다. POST /analyze(analyzer)는 decide_final을,
entities 기반 기존 하네스는 decide를 쓰며 decide도 decide_final로 판정한다.

1. 악성 일치·충돌 → RISK/high (다른 처리의 실패·제한보다 우선)
2. 필수 처리 실패·검색 제한·불완전 추출·LLM 결과 없음 → UNKNOWN
3. RISK/high: 강한 신호 1개 이상, 신호 2개 이상, 규칙 기반 안전장치 일치,
   공식 정보로 확인되지 않은 URL·전화번호와 의심 근거(신호 또는 LLM 의심)의 결합
4. RISK/low(주의): 약한 신호 1개, 미확인 URL·전화번호만 있음, LLM 의심 판단만 있음
5. 나머지 → SAFE. 안전을 보장한다는 뜻이 아니라 위험 신호를 찾지 못했다는 뜻이다.

신호는 judge()가 근거 문구를 확인한 결과여야 한다. 사용자에게는 서버 고정 문구만 보여준다 (SPEC 2.9).
"""

from dataclasses import dataclass
from enum import Enum
from typing import Any, Literal
from urllib.parse import urlsplit

from pydantic import BaseModel

from app.services.extractor import ExtractedEntities
from app.services.llm_judge import SIGNALS, STRONG_SIGNALS, LLMJudgement
from app.services.rule_guard import match_rules

# 신호가 이 개수 이상이면 약한 신호만으로도 RISK/high다
HIGH_RISK_MIN_SIGNALS = 2
# 강한 신호지만 다른 근거 없이 혼자 있으면 약한 신호로 세는 신호
LONE_WEAK_SIGNAL = "기관 사칭"

TYPE_LABELS = {"url": "URL", "phone": "전화번호", "domain": "도메인"}

RiskLevel = Literal["high", "low", "unknown"]
GuideType = Literal["damage_stage", "prevention", "verification"]

REASON_PROCESSING_FAILED = "판별에 필요한 처리를 완료하지 못해 판단을 보류했습니다"
REASON_RETRIEVAL_INCOMPLETE = "유사 수법 검색을 끝까지 완료하지 못해 판단을 보류했습니다"
REASON_INCOMPLETE = "해석하지 못한 URL이 있어 판단을 보류했습니다"
REASON_CONFLICT = "악성 단서와 공식 도메인 정보가 충돌합니다"
REASON_UNRESOLVED = "확인되지 않은 URL·전화번호가 있어 추가 확인이 필요합니다"
REASON_SUSPICIOUS = "의심스러운 표현이 있어 주의가 필요합니다"
REASON_SAFE = "위험 신호가 발견되지 않았습니다"
MALICIOUS_REASONS = {
    "url": "신고된 악성 URL이 포함되어 있습니다",
    "domain": "신고된 악성 도메인이 포함되어 있습니다",
    "phone": "신고된 악성 전화번호가 포함되어 있습니다",
}


class Status(str, Enum):
    RISK = "RISK"
    SAFE = "SAFE"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class Evidence:
    """판정 근거. 원래 식별값은 담지 않는다.

    unresolved: 공식 정보로 확인되지 않은 URL·전화번호가 있음
    incomplete: 해석하지 못한 URL 등 추출이 불완전함
    official_support: 모든 URL이 공식 정보로 확인됨 (참고용, SAFE 조건 아님)
    """

    processing_failed: bool
    retrieval_complete: bool
    judgement: LLMJudgement | None = None
    malicious_types: frozenset[str] = frozenset()
    conflict: bool = False
    unresolved: bool = False
    official_support: bool = False
    incomplete: bool = False
    rule_matches: tuple[str, ...] = ()


class FinalDecision(BaseModel):
    status: Status
    risk_level: RiskLevel
    guide_type: GuideType
    reasons: list[str]


def _final(status: Status, reasons: list[str], *, high: bool = True) -> FinalDecision:
    if status == Status.RISK:
        risk_level, guide_type = ("high", "damage_stage") if high else ("low", "verification")
    elif status == Status.SAFE:
        risk_level, guide_type = "low", "prevention"
    else:
        risk_level, guide_type = "unknown", "verification"
    return FinalDecision(
        status=status, risk_level=risk_level, guide_type=guide_type, reasons=list(dict.fromkeys(reasons))
    )


def _signal_reasons(signals: list[str]) -> list[str]:
    # 목록 밖 표현은 판정에는 쓰되 화면 문구로는 내보내지 않는다
    return [f"{signal} 신호가 확인되었습니다" for signal in signals if signal in SIGNALS]


def decide_final(evidence: Evidence) -> FinalDecision:
    """SPEC 2.10 순서. 악성 일치·충돌이 실패·제한보다 우선한다."""
    judgement = evidence.judgement
    signals = [s.signal for s in judgement.signals] if judgement else []

    # 1. 악성 일치·충돌
    if evidence.conflict or evidence.malicious_types:
        reasons = [REASON_CONFLICT] if evidence.conflict else []
        reasons += [MALICIOUS_REASONS[t] for t in ("url", "domain", "phone") if t in evidence.malicious_types]
        return _final(Status.RISK, reasons + _signal_reasons(signals))

    # 2. 필수 처리 실패·검색 제한·불완전 추출
    if evidence.processing_failed or judgement is None:
        return _final(Status.UNKNOWN, [REASON_PROCESSING_FAILED])
    if not evidence.retrieval_complete:
        return _final(Status.UNKNOWN, [REASON_RETRIEVAL_INCOMPLETE])
    if evidence.incomplete:
        return _final(Status.UNKNOWN, [REASON_INCOMPLETE])

    # 링크가 모두 공식 도메인(official_links)이고 미확인 요소·규칙 일치가 없으면,
    # 발신 표기만으로 잡히기 쉬운 기관 사칭 신호 하나는 의심 근거로 보지 않는다 (SPEC 2.10.1)
    if (
        evidence.official_support
        and not evidence.unresolved
        and not evidence.rule_matches
        and set(signals) == {LONE_WEAK_SIGNAL}
    ):
        return _final(Status.SAFE, [REASON_SAFE])

    # 3~4. 의심 근거가 하나라도 있으면 RISK, 근거의 세기로 high·low를 나눈다
    suspected = bool(signals) or judgement.suspicious
    reasons = _signal_reasons(signals)
    if suspected and not reasons:
        reasons.append(REASON_SUSPICIOUS)
    reasons += [f"{rule} 의심 표현이 있습니다" for rule in evidence.rule_matches]
    if evidence.unresolved:
        reasons.append(REASON_UNRESOLVED)
    if suspected or evidence.rule_matches or evidence.unresolved:
        # 기관 사칭은 발신 표기만으로도 잡히기 쉬워 혼자 있으면 약한 신호로 센다 (SPEC 2.10.1).
        # 다른 신호·규칙·미확인 요소가 함께 있으면 아래 다른 조건으로 high가 된다.
        strong = [s for s in signals if s in STRONG_SIGNALS and s != LONE_WEAK_SIGNAL]
        high = (
            bool(strong)
            or len(signals) >= HIGH_RISK_MIN_SIGNALS
            or bool(evidence.rule_matches)
            or (evidence.unresolved and suspected)
        )
        return _final(Status.RISK, reasons, high=high)

    # 5. 나머지
    return _final(Status.SAFE, [REASON_SAFE])


# --- entities 기반 기존 하네스용 ---

@dataclass
class EntityMatch:
    value: str
    type: Literal["url", "phone", "domain"]
    label: Literal["scam", "official"]


class DecisionResult(BaseModel):
    status: Status
    risk_level: RiskLevel
    reasons: list[str] = []
    matched_cases: int = 0
    guide_type: GuideType
    register_as_pending: bool = False


def _enum_str(v: Any) -> str:
    # ORM 객체의 label/type이 Enum이어도 "scam" 같은 문자열로 비교되게 한다
    return str(getattr(v, "value", v))


def check_blacklist(
    entity_matches: list[EntityMatch],
    matched_cases: int = 0,
) -> DecisionResult | None:
    """scam이 있으면 RISK/high, 없으면 None (→ LLM 판단으로 진행)."""
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


def _has_unconfirmed_element(extracted: ExtractedEntities, entity_matches: list[EntityMatch]) -> bool:
    """공식 정보로 확인되지 않은 URL·전화번호가 있으면 True. URL은 호스트 완전 일치·기본 포트여야 한다."""
    official = {
        (_enum_str(m.type), m.value) for m in entity_matches if _enum_str(m.label) == "official"
    }
    official_domains = {value for kind, value in official if kind == "domain"}
    for url in extracted.urls:
        parts = urlsplit(url)
        if parts.port is not None or parts.hostname not in official_domains:
            return True
    if any(domain not in official_domains for domain in extracted.domains):
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

    final = decide_final(Evidence(
        processing_failed=False,
        retrieval_complete=True,
        judgement=judgement,
        unresolved=_has_unconfirmed_element(extracted, entity_matches),
        incomplete=bool(extracted.unparsed_urls),
        rule_matches=tuple(match_rules(message)),
    ))
    return DecisionResult(
        status=final.status,
        risk_level=final.risk_level,
        reasons=final.reasons,
        matched_cases=matched_cases,
        guide_type=final.guide_type,
        register_as_pending=final.status == Status.RISK,
    )
