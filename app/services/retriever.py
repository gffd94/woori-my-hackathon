"""DB 요소 조회 + 유사도 검색.

기존 함수는 설계서의 entities/cases 테이블을 쓰며 DB 오류를 호출자에게 전달한다.
search_patterns는 SPEC 2.7의 활성 수법 카드(patterns) hybrid 검색이며 오류를 상태로 돌려준다.
"""

import math
import re
import time
import unicodedata
from dataclasses import dataclass

from sqlalchemy import bindparam, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.services.decision import EntityMatch
from app.services.extractor import ExtractedEntities


EMBEDDING_DIMENSIONS = 1536


class ExtractionIncompleteError(ValueError):
    """추출 실패를 정상적인 미등록 결과로 처리하지 않도록 호출자에게 알린다."""


@dataclass
class EntityDetail:
    value: str
    type: str
    label: str
    source: str | None

    def as_match(self) -> EntityMatch:
        return EntityMatch(value=self.value, type=self.type, label=self.label)


@dataclass
class SimilarCase:
    id: int
    message_text: str
    distance: float


def _require_complete(extracted: ExtractedEntities) -> None:
    if extracted.unparsed_urls:
        raise ExtractionIncompleteError('분석하지 못한 URL이 있어 판단을 보류해야 합니다')


def lookup_entities(db: Session, extracted: ExtractedEntities) -> list[EntityMatch]:
    """정확히 일치하는 값과 유형만 반환한다. 공식 도메인의 하위 문자열 검색은 하지 않는다.

    DB의 전화번호는 숫자만, URL·도메인은 extractor와 같은 규칙으로 저장해야 한다.
    기관명은 entities의 조회 유형이 아니므로 조회에서 제외한다.
    불완전 추출 시 scam 근거만 반환한다. 없으면 ExtractionIncompleteError다.
    반환 후 check_blacklist를 먼저 호출하고, 예외는 UNKNOWN으로 처리한다.
    """
    matches = []
    # 불완전 추출 시에도 확정된 사기 근거는 찾는다. 공식 일치는 반환하지 않는다.
    incomplete_filter = " AND label = 'scam'" if extracted.unparsed_urls else ''
    query = text(
        'SELECT value, type, label FROM entities '
        'WHERE type = :type AND value IN :values' + incomplete_filter
    ).bindparams(bindparam('values', expanding=True))
    for entity_type, values in (
        ('url', extracted.urls),
        ('domain', extracted.domains),
        ('phone', extracted.phones),
    ):
        if not values:
            continue
        rows = db.execute(query, {'type': entity_type, 'values': values}).mappings()
        matches.extend(EntityMatch(value=row['value'], type=row['type'], label=row['label']) for row in rows)
    if not matches:
        _require_complete(extracted)
    return matches


def lookup_entity_details(db: Session, extracted: ExtractedEntities) -> list[EntityDetail]:
    """출처 포함 조회. source 컬럼이 필요하며 불완전 추출 시 scam만 반환한다."""
    incomplete_filter = " AND label = 'scam'" if extracted.unparsed_urls else ''
    query = text(
        'SELECT value, type, label, source FROM entities '
        'WHERE type = :type AND value IN :values' + incomplete_filter
    ).bindparams(bindparam('values', expanding=True))
    details = []
    for kind, values in (('url', extracted.urls), ('domain', extracted.domains), ('phone', extracted.phones)):
        if values:
            rows = db.execute(query, {'type': kind, 'values': values}).mappings()
            details.extend(EntityDetail(**row) for row in rows)
    if not details:
        _require_complete(extracted)
    return details


def build_entity_lookup(
    extracted: ExtractedEntities, matches: list[EntityMatch]
) -> dict[str, str | None]:
    """judge(..., entity_lookup=...)에 전달할 값 → label 사전. 미등록은 None."""
    _require_complete(extracted)
    lookup = dict.fromkeys(extracted.urls + extracted.domains + extracted.phones)
    for match in matches:
        if match.value in lookup:
            # 서로 다른 유형에 같은 값이 등록되어도 scam 근거를 우선 보존한다.
            if lookup[match.value] != 'scam':
                lookup[match.value] = match.label
    return lookup


def _vector_parameter(embedding: list[float], limit: int) -> str:
    if type(limit) is not int or not 1 <= limit <= 20:
        raise ValueError('limit은 1~20이어야 합니다')
    if not isinstance(embedding, (list, tuple)) or len(embedding) != EMBEDDING_DIMENSIONS:
        raise ValueError(f'임베딩은 {EMBEDDING_DIMENSIONS}차원이어야 합니다')
    try:
        valid = all(type(value) in (int, float) and math.isfinite(value) for value in embedding)
    except OverflowError:
        valid = False
    if not valid or not any(embedding):
        raise ValueError('임베딩은 유한한 숫자이며 영벡터가 아니어야 합니다')
    return '[' + ','.join(str(float(value)) for value in embedding) + ']'


def search_similar_cases(db: Session, embedding: list[float], limit: int = 3) -> list[str]:
    """기존 LLM용 문구 목록. 임계값 없는 상위 후보이므로 일치 확정 건수가 아니다.

    임베딩은 저장 데이터와 같은 모델·전처리로 생성해야 한다.
    임계값이 필요하면 search_case_details를 사용한다.
    """
    vector = _vector_parameter(embedding, limit)
    query = text(
        "SELECT message_text FROM cases "
        "WHERE status = 'verified' AND embedding IS NOT NULL "
        "AND vector_norm(embedding) > 0 "
        "ORDER BY embedding <=> CAST(:embedding AS vector), id "
        "LIMIT :limit"
    )
    return list(db.execute(query, {'embedding': vector, 'limit': limit}).scalars().all())


def search_case_details(
    db: Session, embedding: list[float], limit: int = 3, *, max_distance: float | None = None
) -> list[SimilarCase]:
    """사례 ID·문구·코사인 거리 반환. 거리는 작을수록 가깝다.

    max_distance는 0~2. 기본은 필터 없음이며 평가 데이터로 기준을 정해 전달한다.
    같은 차원이더라도 모델이 다르면 비교할 수 없다. 모델 선택·관리는 호출자 담당이다.
    """
    vector = _vector_parameter(embedding, limit)
    if max_distance is not None:
        if type(max_distance) not in (int, float) or not 0 <= max_distance <= 2:
            raise ValueError('max_distance는 0~2의 유한한 숫자여야 합니다')
    distance = 'embedding <=> CAST(:embedding AS vector)'
    filter_sql = f'AND ({distance}) <= :max_distance ' if max_distance is not None else ''
    query = text(
        f'SELECT id, message_text, {distance} AS distance FROM cases '
        "WHERE status = 'verified' AND embedding IS NOT NULL "
        'AND vector_norm(embedding) > 0 ' + filter_sql +
        f'ORDER BY {distance}, id LIMIT :limit'
    )
    params = {'embedding': vector, 'limit': limit}
    if max_distance is not None:
        params['max_distance'] = max_distance
    return [SimilarCase(**row) for row in db.execute(query, params).mappings()]


# ── 활성 수법 카드 hybrid 검색 (SPEC 2.7) ─────────────────────────────────

NGRAM_THRESHOLD = 0.35
# 측정(2026-10-27): 짧은 문자와 카드 사이 코사인은 0.3~0.7이라 0.80은 한 건도 통과하지 못했다.
# 카드는 LLM 참고용이고 판정에 직접 쓰지 않으므로, 스미싱에 맞는 카드가 붙는 쪽으로 정했다 (SPEC 2.7.3)
VECTOR_THRESHOLD = 0.43
TOP_K = 5
RRF_K = 60
NGRAM_BATCH_SIZE = 500
SEARCH_BUDGET_SECONDS = 5.0
# 경계값(정확히 0.35·0.43)이 부동소수 오차로 빠지지 않게 하는 허용치
_SCORE_EPSILON = 1e-9
# 마스킹 대체 표기(OOO, ○○, ***, XXX)는 유사도 계산에서 뺀다.
_MASK_TOKEN = re.compile(r'O{2,}|○{2,}|\*{2,}|X{3,}')
_WHITESPACE = re.compile(r'\s+')


@dataclass
class PatternMatch:
    id: int
    name: str
    summary: str | None
    examples: list[str]
    score: float


@dataclass
class PatternRetrieval:
    status: str
    method: str | None
    coverage: str
    reason_code: str | None = None
    patterns: list[PatternMatch] | None = None

    @property
    def matched_cases(self) -> int | None:
        """완료된 검색의 반환 수법 카드 수. 미완료면 None이다."""
        if self.status != 'completed' or self.patterns is None:
            return None
        return len(self.patterns)


def _ngram_text(value: str | None) -> str:
    value = unicodedata.normalize('NFKC', value or '')
    value = _MASK_TOKEN.sub('', value).lower()
    return _WHITESPACE.sub('', value)


def _trigrams(value: str | None) -> frozenset[str]:
    compact = _ngram_text(value)
    return frozenset(compact[i:i + 3] for i in range(len(compact) - 2))


def _jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def ngram_similarity(left: str | None, right: str | None) -> float:
    """전처리 후 공백 제외 연속 3글자 집합의 Jaccard 유사도. 3글자 미만이면 0이다."""
    return _jaccard(_trigrams(left), _trigrams(right))


def top_matches(scores, threshold: float, limit: int = TOP_K) -> list[tuple[int, float]]:
    """임계값 이상만 남기고 점수 내림차순·ID 오름차순으로 상위 limit개를 고른다."""
    passed = [(pid, score) for pid, score in scores if score >= threshold - _SCORE_EPSILON]
    return sorted(passed, key=lambda item: (-item[1], item[0]))[:limit]


def rrf_merge(*rankings: list[int], limit: int = TOP_K) -> list[int]:
    """Reciprocal rank fusion. 같은 카드는 한 번만 세고 동점은 ID 오름차순이다."""
    scores: dict[int, float] = {}
    for ranking in rankings:
        for rank, pid in enumerate(ranking, start=1):
            scores[pid] = scores.get(pid, 0.0) + 1 / (RRF_K + rank)
    return sorted(scores, key=lambda pid: (-scores[pid], pid))[:limit]


def _example_texts(example_messages) -> list[str]:
    return [
        example['text'].strip()
        for example in example_messages or []
        if isinstance(example, dict) and isinstance(example.get('text'), str) and example['text'].strip()
    ]


def _is_postgres(db) -> bool:
    try:
        return db.get_bind().dialect.name == 'postgresql'
    except Exception:
        return False


class _BudgetExceeded(Exception):
    pass


def search_patterns(
    db: Session,
    message: str,
    embedding: list[float] | None,
    *,
    budget: float = SEARCH_BUDGET_SECONDS,
    clock=time.monotonic,
) -> PatternRetrieval:
    """활성 수법 카드 전체를 n-gram과 pgvector로 검색해 RRF로 최대 5개를 고른다.

    message는 마스킹된 문자여야 하고, embedding은 트랜잭션 밖에서 미리 만든 질의 벡터다.
    PostgreSQL에서는 읽기 전용 REPEATABLE READ 스냅샷으로 검색하므로 이 함수 전용의
    새 Session을 넘겨야 하며, 끝나면 rollback한다. 예외 대신 상태로 결과를 돌려준다.
    """
    if embedding is None:
        return PatternRetrieval('limited', 'ngram', 'limited', 'text_only')
    try:
        vector = _vector_parameter(embedding, TOP_K)
    except ValueError:
        return PatternRetrieval('failed', None, 'unknown', 'embedding_invalid')

    started = clock()
    postgres = _is_postgres(db)

    def before_query() -> None:
        remaining = budget - (clock() - started)
        if remaining <= 0:
            raise _BudgetExceeded
        if postgres:
            db.execute(text(f"SET LOCAL statement_timeout = '{max(int(remaining * 1000), 1)}ms'"))

    try:
        if postgres:
            db.execute(text('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY'))
        before_query()
        coverage = db.execute(text(
            'SELECT count(*) AS total, count(embedding) AS filled, '
            'count(*) FILTER (WHERE embedding IS NOT NULL AND '
            f'(vector_dims(embedding) <> {EMBEDDING_DIMENSIONS} OR vector_norm(embedding) = 0)) AS invalid '
            'FROM patterns WHERE is_active'
        )).mappings().one()
        if coverage['filled'] < coverage['total']:
            return PatternRetrieval('limited', 'hybrid', 'limited', 'vector_missing')
        if coverage['invalid']:
            return PatternRetrieval('limited', 'hybrid', 'limited', 'vector_invalid')
        if coverage['total'] == 0:
            return PatternRetrieval('completed', 'hybrid', 'complete', patterns=[])

        query_grams = _trigrams(message)
        ngram_best: list[tuple[int, float]] = []
        after = 0
        while True:
            before_query()
            rows = db.execute(
                text(
                    'SELECT id, summary, example_messages FROM patterns '
                    'WHERE is_active AND id > :after ORDER BY id LIMIT :batch'
                ),
                {'after': after, 'batch': NGRAM_BATCH_SIZE},
            ).mappings().all()
            if not rows:
                break
            scored = [
                (row['id'], max(
                    _jaccard(query_grams, _trigrams(t))
                    for t in [row['summary'], *_example_texts(row['example_messages'])]
                ))
                for row in rows
            ]
            ngram_best = top_matches(ngram_best + scored, NGRAM_THRESHOLD)
            if len(rows) < NGRAM_BATCH_SIZE:
                break
            after = rows[-1]['id']

        before_query()
        nearest = db.execute(
            text(
                'SELECT id, embedding <=> CAST(:embedding AS vector) AS distance FROM patterns '
                'WHERE is_active AND embedding IS NOT NULL '
                'ORDER BY distance, id LIMIT :limit'
            ),
            {'embedding': vector, 'limit': TOP_K},
        ).mappings().all()
        vector_best = top_matches(
            [(row['id'], 1 - float(row['distance'])) for row in nearest], VECTOR_THRESHOLD
        )

        ngram_rank = {pid: rank for rank, (pid, _) in enumerate(ngram_best, 1)}
        vector_rank = {pid: rank for rank, (pid, _) in enumerate(vector_best, 1)}
        merged = rrf_merge(list(ngram_rank), list(vector_rank))
        patterns: list[PatternMatch] = []
        if merged:
            before_query()
            details = {
                row['id']: row
                for row in db.execute(
                    text(
                        'SELECT id, name, summary, example_messages FROM patterns WHERE id IN :ids'
                    ).bindparams(bindparam('ids', expanding=True)),
                    {'ids': merged},
                ).mappings().all()
            }
            for pid in merged:
                row = details[pid]
                score = sum(1 / (RRF_K + ranks[pid]) for ranks in (ngram_rank, vector_rank) if pid in ranks)
                patterns.append(PatternMatch(
                    id=pid, name=row['name'], summary=row['summary'],
                    examples=_example_texts(row['example_messages']), score=score,
                ))
        if clock() - started > budget:
            return PatternRetrieval('limited', 'hybrid', 'limited', 'time_budget')
        return PatternRetrieval('completed', 'hybrid', 'complete', patterns=patterns)
    except _BudgetExceeded:
        return PatternRetrieval('limited', 'hybrid', 'limited', 'time_budget')
    except SQLAlchemyError:
        return PatternRetrieval('failed', 'hybrid', 'unknown', 'db_error')
    finally:
        try:
            db.rollback()
        except SQLAlchemyError:
            pass
