"""analyzer 호출 경계의 실제 DB 구현: 대조(lookup)·검색(search)·기록(save).

각 함수는 호출마다 새 Session을 연다. search_patterns가 전용 Session을 요구하고(SPEC 2.7),
대조·검색 실패가 기록 저장 트랜잭션에 섞이지 않게 하기 위해서다.
DB 오류는 그대로 올려 보낸다. analyzer가 단계별로 UNKNOWN·503으로 바꾼다.
"""

from collections.abc import Callable

from sqlalchemy import bindparam, text
from sqlalchemy.orm import Session

from app.services.analyzer import IndicatorMatch, LookupResult, PatternCard, SearchOutcome, VerdictRecord
from app.services.extractor import ExtractedEntities
from app.services.retriever import search_patterns
from app.schemas.analyze import ReferenceSource

SessionFactory = Callable[[], Session]

_INDICATOR_SQL = text(
    "SELECT id, type, value_normalized FROM indicators "
    "WHERE type = :type AND value_normalized IN :values"
).bindparams(bindparam("values", expanding=True))

_OFFICIAL_SQL = text(
    "SELECT domain, organization, verification_reference FROM official_links WHERE domain IN :domains"
).bindparams(bindparam("domains", expanding=True))

_SOURCE_SQL = text(
    'SELECT ps.pattern_id, s.id, s.title, s.site, s.url, s.posted_date '
    'FROM pattern_sources ps JOIN sources s ON s.id = ps.source_id '
    'WHERE ps.pattern_id IN :ids ORDER BY ps.pattern_id, s.id'
).bindparams(bindparam('ids', expanding=True))

_INSERT_VERDICT_SQL = text(
    "INSERT INTO verdict_logs "
    "(message_masked, verdict, score, matched_pattern_ids, matched_indicator_ids, reasoning, model_version) "
    "VALUES (:message_masked, :verdict, :score, :matched_pattern_ids, :matched_indicator_ids, "
    ":reasoning, :model_version)"
)


def lookup_indicators(extracted: ExtractedEntities, *, session_factory: SessionFactory) -> LookupResult:
    """추출 값과 정확히 같은 정규화 값만 일치로 본다. 하위 도메인은 합치지 않는다 (SPEC 2.6)."""
    groups = {"url": extracted.urls, "domain": extracted.domains, "phone": extracted.phones}
    if not any(groups.values()):
        return LookupResult()

    matches: list[IndicatorMatch] = []
    official: frozenset[str] = frozenset()
    official_sources = {}
    with session_factory() as db:
        for kind, values in groups.items():
            if not values:
                continue
            rows = db.execute(_INDICATOR_SQL, {"type": kind, "values": list(values)}).mappings().all()
            matches += [IndicatorMatch(id=row["id"], type=kind, value=row["value_normalized"]) for row in rows]
        if extracted.domains:
            rows = db.execute(_OFFICIAL_SQL, {"domains": list(extracted.domains)}).mappings().all()
            official = frozenset(row["domain"] for row in rows)
            official_sources = {
                row['domain']: ReferenceSource(
                    title=row.get('organization') or '공식 도메인 확인 자료',
                    site=row.get('organization'), url=row.get('verification_reference'))
                for row in rows
            }
        db.rollback()
    return LookupResult(indicators=tuple(matches), official_domains=official, official_sources=official_sources)


def search_cards(masked: str, vector: list[float], *, session_factory: SessionFactory) -> SearchOutcome:
    """search_patterns 결과를 analyzer의 SearchOutcome으로 옮긴다. 미완료면 카드를 넘기지 않는다."""
    with session_factory() as db:
        result = search_patterns(db, masked, vector)
    sources = {}
    if result.status == 'completed' and result.patterns:
        ids = list(dict.fromkeys(p.id for p in result.patterns))
        # 검색 함수가 트랜잭션을 관리하므로 메타데이터는 별도 세션에서 조회한다.
        with session_factory() as db:
            rows = db.execute(_SOURCE_SQL, {'ids': ids}).mappings().all()
            for row in rows:
                if row['pattern_id'] not in ids:
                    continue
                source = ReferenceSource(title=row['title'] or '제목 없는 참고 자료',
                    site=row['site'], url=row['url'], posted_date=row['posted_date'])
                group = sources.setdefault(row['pattern_id'], [])
                if source not in group:
                    group.append(source)
            db.rollback()
    if result.status != "completed":
        return SearchOutcome(status=result.status, method=result.method, coverage=result.coverage)
    cards = tuple(PatternCard(id=p.id, name=p.name, summary=p.summary,
        sources=tuple(sources.get(p.id, ()))) for p in result.patterns or [])
    return SearchOutcome(status="completed", method=result.method, coverage=result.coverage, patterns=cards)


def save_verdict(record: VerdictRecord, *, session_factory: SessionFactory) -> None:
    """기록이 확정(commit)되어야 응답한다. 실패하면 예외를 올려 503이 되게 한다 (SPEC 2.11)."""
    with session_factory() as db:
        try:
            db.execute(_INSERT_VERDICT_SQL, {
                "message_masked": record.message_masked,
                "verdict": record.verdict,
                "score": record.score,
                "matched_pattern_ids": list(record.matched_pattern_ids),
                "matched_indicator_ids": list(record.matched_indicator_ids),
                "reasoning": record.reasoning,
                "model_version": record.model_version,
            })
            db.commit()
        except Exception:
            db.rollback()
            raise
