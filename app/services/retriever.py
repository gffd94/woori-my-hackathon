"""DB 요소 조회 + verified 사례의 벡터 유사도 검색.

설계서의 entities/cases 테이블과 동기 SQLAlchemy Session을 사용한다.
DB 오류는 호출자에게 전달한다. 라우터는 오류 시 UNKNOWN으로 처리해야 한다.
"""

import math
from dataclasses import dataclass

from sqlalchemy import bindparam, text
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
