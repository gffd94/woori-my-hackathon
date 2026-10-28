"""POST /analyze 핵심 흐름: 추출 → 대조 → 임베딩 → 검색 → 최소화 → LLM → 판정 → 기록.

DB 대조·검색·임베딩·LLM·기록 저장은 생성자로 받는 함수(호출 경계)다.
팀원 구현이 바뀌어도 아래 입출력 형태만 지키면 이 흐름은 그대로 동작한다.

- lookup(extracted) -> LookupResult       indicators·official_links 대조
- embed(masked_text) -> list[float]        질의 임베딩 (1536차원)
- search(masked_text, vector) -> SearchOutcome   patterns 검색
- judge(masked_text, cards, entity_lookup) -> LLMJudgement | None
- save(VerdictRecord) -> None              verdict_logs 저장. 예외면 503
"""

import ipaddress
import logging
import os
from dataclasses import dataclass, field
from functools import partial
from typing import Callable, Literal
from urllib.parse import SplitResult, urlsplit

from app.config import Settings
from app.schemas.analyze import AnalysisEvidence, AnalyzeResponse, ReferenceSource, RetrievalInfo
from app.services.decision import Evidence, decide_final
from app.services.embedding import request_embedding, validate_embedding
from app.services.extractor import ExtractedEntities, extract_entities
from app.services.llm_judge import LLMJudgement, judge as llm_judge
from app.services.masking import mask_text, mask_url
from app.services.rule_guard import match_rules

logger = logging.getLogger(__name__)

MAX_PATTERNS = 5
MAX_CARD_CHARS = 300

NOT_RUN = RetrievalInfo(status="not_run", method=None, coverage="unknown")
FAILED = RetrievalInfo(status="failed", method=None, coverage="unknown")


@dataclass(frozen=True)
class IndicatorMatch:
    id: int
    type: Literal["url", "domain", "phone"]
    value: str


@dataclass(frozen=True)
class LookupResult:
    indicators: tuple[IndicatorMatch, ...] = ()
    official_domains: frozenset[str] = frozenset()
    official_sources: dict[str, ReferenceSource] = field(default_factory=dict)


@dataclass(frozen=True)
class PatternCard:
    id: int
    name: str
    summary: str | None = None
    impersonation: str | None = None
    lure_action: str | None = None
    triggers: tuple[str, ...] = ()
    sources: tuple[ReferenceSource, ...] = ()


@dataclass(frozen=True)
class SearchOutcome:
    status: Literal["completed", "limited", "failed"]
    method: Literal["hybrid", "ngram"] | None
    coverage: Literal["complete", "limited", "unknown"]
    patterns: tuple[PatternCard, ...] = ()


@dataclass(frozen=True)
class VerdictRecord:
    """verdict_logs에 넘길 최소화된 기록. score·model_version 확정 전에는 None일 수 있다."""

    message_masked: str
    verdict: str
    score: float | None
    matched_pattern_ids: tuple[int, ...]
    matched_indicator_ids: tuple[int, ...]
    reasoning: str
    model_version: str | None


class VerdictLogError(Exception):
    """판정 기록 저장 실패. 라우터가 503으로 바꾼다."""


Lookup = Callable[[ExtractedEntities], LookupResult]
Embed = Callable[[str], list[float]]
Search = Callable[[str, list[float]], SearchOutcome]
Judge = Callable[[str, list[str], dict[str, str | None]], LLMJudgement | None]
Save = Callable[[VerdictRecord], None]


class Analyzer:
    def __init__(
        self,
        *,
        lookup: Lookup,
        embed: Embed,
        search: Search,
        judge: Judge,
        save: Save,
        model_version: str | None = None,
    ) -> None:
        self._lookup = lookup
        self._embed = embed
        self._search = search
        self._judge = judge
        self._save = save
        self._model_version = model_version

    def analyze(self, message: str) -> AnalyzeResponse:
        extracted = extract_entities(message)
        masked = mask_text(message)
        elements: _Elements | None = None
        retrieval, patterns = NOT_RUN, ()
        judgement = None
        lookup = None

        try:
            lookup = self._lookup(extracted)
            elements = _evaluate(extracted, lookup)
        except Exception as exc:
            _log_failure("lookup", exc)

        # 대조가 실패하면 검색·LLM을 실행하지 않는다 (not_run). 실행하지 않은 단계를 성공으로 보지 않는다.
        if elements is not None:
            retrieval, patterns = self._retrieve(masked)
            if retrieval.status == "completed":
                judgement = self._call_judge(masked, patterns, elements.labels)

        complete = retrieval.status == "completed"
        decision = decide_final(Evidence(
            processing_failed=elements is None,
            retrieval_complete=complete,
            judgement=judgement,
            malicious_types=elements.malicious_types if elements else frozenset(),
            conflict=elements.conflict if elements else False,
            unresolved=elements.unresolved if elements else False,
            official_support=elements.official_support if elements else False,
            incomplete=elements.incomplete if elements else False,
            # 규칙 안전장치는 외부로 보내지 않으므로 원문으로 확인한다 (SPEC 2.10.3)
            rule_matches=tuple(match_rules(message)),
        ))

        record = VerdictRecord(
            message_masked=masked,
            verdict=decision.status.value,
            score=None,  # 산정 방식 미확정 (SPEC 2.5.4)
            matched_pattern_ids=tuple(p.id for p in patterns) if complete else (),
            matched_indicator_ids=elements.indicator_ids if elements else (),
            reasoning=" / ".join(decision.reasons),
            model_version=self._model_version,
        )
        try:
            self._save(record)
        except Exception as exc:
            _log_failure("save", exc)
            raise VerdictLogError("판정 기록 저장에 실패했습니다") from None

        return AnalyzeResponse(
            status=decision.status,
            risk_level=decision.risk_level,
            reasons=decision.reasons,
            matched_cases=len(patterns) if complete else None,
            guide_type=decision.guide_type,
            retrieval=retrieval,
            evidence=_response_evidence(elements, lookup, patterns, judgement, masked, decision.status.value),
        )

    def _retrieve(self, masked: str) -> tuple[RetrievalInfo, tuple[PatternCard, ...]]:
        # 질의 임베딩은 검색 전에 만든다 (SPEC 2.7.1)
        try:
            vector = validate_embedding(self._embed(masked))
        except Exception as exc:
            _log_failure("embed", exc)
            return FAILED, ()
        try:
            outcome = self._search(masked, vector)
        except Exception as exc:
            _log_failure("search", exc)
            return FAILED, ()
        if not isinstance(outcome, SearchOutcome) or outcome.status == "failed":
            return FAILED, ()

        # n-gram 단독이나 부분 결과는 완전 검색이 아니다. 부분 결과 수도 내보내지 않는다.
        if (outcome.status, outcome.method, outcome.coverage) != ("completed", "hybrid", "complete"):
            return RetrievalInfo(status="limited", method=outcome.method, coverage="limited"), ()

        unique = tuple({card.id: card for card in outcome.patterns}.values())[:MAX_PATTERNS]
        return RetrievalInfo(status="completed", method="hybrid", coverage="complete"), unique

    def _call_judge(
        self, masked: str, patterns: tuple[PatternCard, ...], labels: dict[str, str | None]
    ) -> LLMJudgement | None:
        cards = [_card_text(card) for card in patterns]
        try:
            result = self._judge(masked, cards, labels)
        except Exception as exc:
            _log_failure("judge", exc)
            return None
        return result if isinstance(result, LLMJudgement) else None


def _response_evidence(elements, lookup, patterns, judgement, masked, status):
    """실제 대조·완료 검색에 사용한 자료만 반환한다. 자료를 AI가 생성하지 않는다."""
    evidence = []
    if elements:
        for value, label in elements.labels.items():
            if label in ('scam', 'conflict'):
                evidence.append(AnalysisEvidence(
                    kind='indicator_match', title='등록된 악성 단서 일치', value=value,
                    detail='악성 단서 DB와 일치했어요.' + (' 공식 정보와도 충돌해요.' if label == 'conflict' else '')
                        + ' 이 단서의 원자료 출처는 연결되어 있지 않아요.'))
            elif label == 'official':
                host = urlsplit(value).hostname
                source = lookup.official_sources.get(host) if lookup else None
                evidence.append(AnalysisEvidence(
                    kind='official_match', title='공식 도메인 확인', value=value,
                    detail='등록된 공식 도메인과 일치해요. 문자 전체의 안전을 보장하지는 않아요.',
                    sources=[source] if source else []))
            else:
                evidence.append(AnalysisEvidence(
                    kind='unverified', title='공식 정보 미확인', value=value,
                    detail='공식 정보로 확인되지 않은 요소예요. 악성 정보와 일치했다는 뜻은 아니에요.'))
    if judgement and status == 'RISK':
        for signal in judgement.signals:
            quote = signal.evidence.strip()
            if quote and quote in masked:
                evidence.append(AnalysisEvidence(
                    kind='signal', title=f'{mask_text(signal.signal)[:80]} 신호',
                    value=mask_text(quote)[:300], detail='문자에서 확인한 문구를 바탕으로 분석한 신호예요.'))
    for card in patterns:
        sources = []
        for source in card.sources:
            if source not in sources:
                sources.append(source)
        evidence.append(AnalysisEvidence(
            kind='pattern', title=mask_text(card.name)[:300],
            detail='분석에 참고한 유사 수법이에요. 문자 속 링크의 악성 여부를 직접 증명하는 자료는 아니에요.',
            sources=sources))
    return evidence


@dataclass(frozen=True)
class _Elements:
    """추출 요소별 대조 결과. labels는 LLM에 넘길 마스킹된 값 → scam/official/conflict/None."""

    malicious_types: frozenset[str]
    conflict: bool
    unresolved: bool
    official_support: bool
    indicator_ids: tuple[int, ...]
    incomplete: bool = False
    labels: dict[str, str | None] = field(default_factory=dict)


def _is_plain_official_url(parts: SplitResult) -> bool:
    """공식 도메인 일치만으로 URL 전체를 믿지 않는다 (SPEC 2.6)."""
    if parts.scheme != "https" or parts.port is not None or parts.query or parts.fragment:
        return False
    if parts.username is not None:
        return False
    try:
        ipaddress.ip_address(parts.hostname or "")
    except ValueError:
        return True
    return False


def _evaluate(extracted: ExtractedEntities, lookup: LookupResult) -> _Elements:
    hits = {(match.type, match.value): match.id for match in lookup.indicators}
    malicious_types: set[str] = set()
    indicator_ids: list[int] = []
    labels: dict[str, str | None] = {}
    conflict = False
    # 해석하지 못한 URL·사용자정보 URL은 평가를 끝낼 수 없다 (불완전 추출 → UNKNOWN)
    incomplete = bool(extracted.unparsed_urls)
    # 공식 정보로 확인되지 않은 URL·전화번호 (→ RISK 근거)
    unresolved = False
    official_urls = 0

    for url in extracted.urls:
        parts = urlsplit(url)
        host = parts.hostname
        url_hit = hits.get(("url", url))
        domain_hit = hits.get(("domain", host))
        is_official = host in lookup.official_domains
        for kind, hit in (("url", url_hit), ("domain", domain_hit)):
            if hit is not None:
                malicious_types.add(kind)
                indicator_ids.append(hit)

        if domain_hit is not None and is_official:
            conflict = True
            label = "conflict"
        elif url_hit is not None or domain_hit is not None:
            label = "scam"
        elif is_official and _is_plain_official_url(parts):
            label = "official"
            official_urls += 1
        else:
            label = None
            unresolved = True
        labels[mask_url(url)] = label

    # 공식 전화번호 데이터가 없으므로 악성 일치가 아닌 번호는 미확인이다
    for number, phone in enumerate(extracted.phones, 1):
        hit = hits.get(("phone", phone))
        if hit is not None:
            malicious_types.add("phone")
            indicator_ids.append(hit)
        else:
            unresolved = True
        labels[f"[전화번호 {number}]"] = "scam" if hit is not None else None

    return _Elements(
        malicious_types=frozenset(malicious_types),
        conflict=conflict,
        unresolved=unresolved,
        official_support=bool(extracted.urls) and official_urls == len(extracted.urls),
        indicator_ids=tuple(dict.fromkeys(indicator_ids)),
        labels=labels,
        incomplete=incomplete,
    )


def _card_text(card: PatternCard) -> str:
    parts = [
        card.name,
        card.summary,
        f"사칭: {card.impersonation}" if card.impersonation else None,
        f"유도: {card.lure_action}" if card.lure_action else None,
        f"키워드: {', '.join(card.triggers)}" if card.triggers else None,
    ]
    return mask_text(" / ".join(part for part in parts if part))[:MAX_CARD_CHARS]


def _log_failure(stage: str, exc: Exception) -> None:
    # 예외 문구에 원문·비밀값이 섞일 수 있어 종류만 남긴다 (SPEC 2.14)
    logger.warning("analyze.%s_failed error_type=%s", stage, type(exc).__name__)


# --- 운영 연결 ---
# DB 연결이 없으면 가짜 성공을 돌려주지 않고 실패시킨다: 대조 실패 → UNKNOWN, 기록 실패 → 503.

# llm_judge.call_openai의 기본 모델과 같아야 한다
DEFAULT_LLM_MODEL = "gpt-4o-mini"


def _judge_with_llm(masked: str, cards: list[str], labels: dict[str, str | None]) -> LLMJudgement | None:
    return llm_judge(masked, cards, entity_lookup=labels)


def _new_session():
    # DATABASE_URL이 없어도 앱 시작·요청 검증은 되도록 첫 DB 사용 시점에 엔진을 만든다
    from app.db.session import get_session_factory

    return get_session_factory()()


def build_default_analyzer(settings: Settings) -> Analyzer:
    # repository가 이 모듈의 자료형을 쓰므로 순환 import를 피해 여기서 가져온다
    from app.services import repository

    return Analyzer(
        lookup=partial(repository.lookup_indicators, session_factory=_new_session),
        embed=partial(request_embedding, settings=settings),
        search=partial(repository.search_cards, session_factory=_new_session),
        judge=_judge_with_llm,
        save=partial(repository.save_verdict, session_factory=_new_session),
        # verdict_logs.model_version은 NOT NULL이다. LLM_* 통일 전에는 llm_judge가 쓰는 OPENAI_MODEL을 따른다.
        model_version=settings.llm_model or os.getenv("OPENAI_MODEL", DEFAULT_LLM_MODEL),
    )
