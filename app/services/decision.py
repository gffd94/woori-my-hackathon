"""RISK/SAFE/UNKNOWN 최종 분기

신규 흐름(POST /analyze)은 아래 decide_final을 쓴다 (SPEC 2.10).
check_blacklist·decide·DecisionResult는 entities/cases 기반 기존 하네스용이며,
retriever를 ERD로 바꿀 때 함께 정리한다.

[기존 decide 규칙]
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

from app.services.llm_judge import SIGNALS, LLMJudgement

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


# --- SPEC 2.10 최종 판정 (POST /analyze) ---

RiskLevel = Literal["high", "low", "unknown"]
GuideType = Literal["damage_stage", "prevention", "verification"]

VERDICT_FIELDS: dict[Status, tuple[RiskLevel, GuideType]] = {
    Status.RISK: ("high", "damage_stage"),
    Status.SAFE: ("low", "prevention"),
    Status.UNKNOWN: ("unknown", "verification"),
}

# 사용자에게 보여줄 이유는 서버 고정 문구만 쓴다. LLM의 자유 문장은 내보내지 않는다 (SPEC 2.9).
REASON_PROCESSING_FAILED = "판별에 필요한 처리를 완료하지 못해 판단을 보류했습니다"
REASON_RETRIEVAL_INCOMPLETE = "유사 수법 검색을 끝까지 완료하지 못해 판단을 보류했습니다"
REASON_CONFLICT = "악성 단서와 공식 도메인 정보가 충돌합니다"
REASON_UNRESOLVED = "확인되지 않은 URL·전화번호가 있어 추가 확인이 필요합니다"
REASON_INSUFFICIENT = "안전하다고 판단할 근거가 부족합니다"
REASON_SAFE = "공식 도메인과 일치하고 위험 신호가 발견되지 않았습니다"
MALICIOUS_REASONS = {
    "url": "신고된 악성 URL이 포함되어 있습니다",
    "domain": "신고된 악성 도메인이 포함되어 있습니다",
    "phone": "신고된 악성 전화번호가 포함되어 있습니다",
}


@dataclass(frozen=True)
class Evidence:
    """analyzer가 모은 판정 근거. 원래 식별값은 담지 않는다."""

    processing_failed: bool
    retrieval_complete: bool
    judgement: LLMJudgement | None = None
    malicious_types: frozenset[str] = frozenset()
    conflict: bool = False
    unresolved: bool = False
    official_support: bool = False


class FinalDecision(BaseModel):
    status: Status
    risk_level: RiskLevel
    guide_type: GuideType
    reasons: list[str]


def _final(status: Status, reasons: list[str]) -> FinalDecision:
    risk_level, guide_type = VERDICT_FIELDS[status]
    return FinalDecision(
        status=status, risk_level=risk_level, guide_type=guide_type, reasons=list(dict.fromkeys(reasons))
    )


def _signal_reasons(judgement: LLMJudgement) -> list[str]:
    # 목록 밖 표현은 SAFE 차단에는 쓰되 화면 문구로는 내보내지 않는다
    return [f"{signal} 신호가 확인되었습니다" for signal in judgement.signals if signal in SIGNALS]


def decide_final(evidence: Evidence) -> FinalDecision:
    """SPEC 2.10 순서. 실패·제한이 악성 일치·충돌보다 우선한다."""
    # 1. 필수 처리 실패·검색 제한
    if evidence.processing_failed:
        return _final(Status.UNKNOWN, [REASON_PROCESSING_FAILED])
    if not evidence.retrieval_complete:
        return _final(Status.UNKNOWN, [REASON_RETRIEVAL_INCOMPLETE])
    judgement = evidence.judgement
    if judgement is None:
        return _final(Status.UNKNOWN, [REASON_PROCESSING_FAILED])

    # 2~3. 악성 일치·충돌·명확한 위험 신호
    clear_risk = judgement.is_high_risk and len(judgement.signals) >= HIGH_RISK_MIN_SIGNALS
    if evidence.conflict or evidence.malicious_types or clear_risk:
        reasons = [REASON_CONFLICT] if evidence.conflict else []
        reasons += [MALICIOUS_REASONS[t] for t in ("url", "domain", "phone") if t in evidence.malicious_types]
        if clear_risk:
            reasons += _signal_reasons(judgement) or ["여러 위험 신호가 함께 발견되었습니다"]
        return _final(Status.RISK, reasons)

    # 4. 미확인·불완전 평가
    if evidence.unresolved:
        return _final(Status.UNKNOWN, [REASON_UNRESOLVED])

    # 5. 공식 근거·위험 부재·LLM SAFE 제안을 모두 갖춰야 SAFE
    if (
        evidence.official_support
        and not judgement.is_high_risk
        and not judgement.signals
        and judgement.suggestion == "SAFE"
    ):
        return _final(Status.SAFE, [REASON_SAFE])

    # 6. 나머지
    return _final(Status.UNKNOWN, [REASON_INSUFFICIENT])