"""외부 API 없이 네 서비스의 연결 계약을 검증하는 하네스.

SQLite에서는 pgvector 연산자만 코사인 거리 함수로 대체한다.
실제 PostgreSQL SQL 검증은 test_pgvector_integration.py가 담당한다.
이 파일의 run_pipeline은 테스트용이며 운영 라우터 구현이 아니다.
"""

import json
import math

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.services.decision import Status, check_blacklist, decide
from app.services.extractor import extract
from app.services.llm_judge import judge
from app.services.retriever import build_entity_lookup, lookup_entities, search_similar_cases, search_case_details


VECTOR = [1.0] + [0.0] * 1535


def vector_norm(value):
    return math.sqrt(sum(x * x for x in json.loads(value)))


def cosine_distance(left, right):
    a, b = json.loads(left), json.loads(right)
    return 1 - sum(x * y for x, y in zip(a, b)) / (vector_norm(left) * vector_norm(right))


class LocalVectorDB:
    """필터·정렬·LIMIT은 SQL로 실행하고 벡터 연산만 대체한다."""

    def __init__(self, session):
        self.session = session
        self.fail_on = None

    def execute(self, statement, parameters):
        sql = str(statement)
        stage = 'search' if 'FROM cases' in sql else 'lookup'
        if self.fail_on == stage:
            raise SQLAlchemyError('테스트용 DB 장애')
        if stage == 'search':
            sql = sql.replace(
                'embedding <=> CAST(:embedding AS vector)',
                'cosine_distance(embedding, :embedding)',
            )
            statement = text(sql)
        return self.session.execute(statement, parameters)


@pytest.fixture
def harness_db():
    engine = create_engine('sqlite://')
    with engine.connect() as connection:
        native = connection.connection.driver_connection
        native.create_function('vector_norm', 1, vector_norm)
        native.create_function('cosine_distance', 2, cosine_distance)
        with Session(bind=connection) as session:
            session.execute(text('CREATE TABLE entities (value TEXT, type TEXT, label TEXT)'))
            session.execute(text("INSERT INTO entities VALUES "
                                 "('official.example', 'domain', 'official'), "
                                 "('scam.example', 'domain', 'scam')"))
            session.execute(text('CREATE TABLE cases (id INTEGER, message_text TEXT, status TEXT, embedding TEXT)'))
            rows = [
                (1, '미검증 가까운 사례', 'pending', VECTOR),
                (2, '반려된 가까운 사례', 'rejected', VECTOR),
                (3, '가상기관 인증 요구 사례', 'verified', VECTOR),
                (4, '가상 택배 사례', 'verified', [0.0, 1.0] + [0.0] * 1534),
                (5, '영벡터 사례', 'verified', [0.0] * 1536),
                (6, '임베딩 없는 사례', 'verified', None),
            ]
            for case_id, message, status, vector in rows:
                session.execute(text('INSERT INTO cases VALUES (:id, :message, :status, :vector)'),
                                dict(id=case_id, message=message, status=status,
                                     vector=json.dumps(vector) if vector is not None else None))
            yield LocalVectorDB(session)
    engine.dispose()


def run_pipeline(db, message, llm_call):
    extracted = extract(message, ['가상은행'])
    matches = []
    try:
        matches = lookup_entities(db, extracted)
        blacklisted = check_blacklist(matches)
        if blacklisted is not None:
            return blacklisted
        cases = search_similar_cases(db, VECTOR)
    except (SQLAlchemyError, ValueError):
        # DB 장애를 빈 검색 결과로 오인하지 않고 UNKNOWN으로 처리한다.
        return decide(matches, None)
    judgement = judge(message, cases, llm_call,
                      entity_lookup=build_entity_lookup(extracted, matches))
    return decide(matches, judgement, matched_cases=len(cases))


@pytest.mark.parametrize('message,high_risk,signals,expected', [
    ('가상은행 계좌 정지 https://new.example 인증 요청', True,
     ['기관 사칭', '인증 요구'], Status.RISK),
    ('가상은행 결제 안내 https://official.example', False, [], Status.SAFE),
    ('특별 지원금 문의010-0000-0000입니다', False,
     ['개인 번호로 연락 유도'], Status.UNKNOWN),
    ('DB 미등록 기관 사칭 https://unseen.example 앱 설치 요구', True,
     ['기관 사칭', '앱 설치 유도'], Status.RISK),
    ('공식 주소와 인증 요구 https://official.example', True,
     ['기관 사칭', '인증 요구'], Status.RISK),
    ('https://official.example.evil.test 결제 안내', False, [], Status.UNKNOWN),
])
def test_design_scenarios(harness_db, message, high_risk, signals, expected):
    prompts = []

    def fake_llm(system, user):
        prompts.append(user)
        return json.dumps(dict(is_high_risk=high_risk, signals=signals,
                               reasons=['테스트 근거'], category=None))

    result = run_pipeline(harness_db, message, fake_llm)
    assert result.status == expected
    assert result.matched_cases == 2
    assert result.register_as_pending == (expected == Status.RISK)
    assert '가상기관 인증 요구 사례' in prompts[0]
    assert '미검증 가까운 사례' not in prompts[0]
    assert '반려된 가까운 사례' not in prompts[0]
    assert '영벡터 사례' not in prompts[0]


def test_blacklist_short_circuits_search_and_llm(harness_db):
    harness_db.fail_on = 'search'

    def must_not_call(*args):
        pytest.fail('블랙리스트 일치 시 LLM을 호출하면 안 됩니다')

    result = run_pipeline(harness_db, 'https://official.example https://scam.example', must_not_call)
    assert result.status == Status.RISK
    assert not result.register_as_pending


@pytest.mark.parametrize('stage', ['lookup', 'search'])
def test_db_errors_do_not_become_safe(harness_db, stage):
    harness_db.fail_on = stage

    def must_not_call(*args):
        pytest.fail('DB 장애 후 정상 LLM 흐름으로 진행하면 안 됩니다')

    assert run_pipeline(harness_db, 'https://official.example', must_not_call).status == Status.UNKNOWN


@pytest.mark.parametrize('failure', ['invalid_json', 'timeout'])
def test_llm_errors_do_not_become_safe(harness_db, failure):
    def fake_llm(*args):
        if failure == 'timeout':
            raise TimeoutError('테스트용 시간 초과')
        return 'JSON이 아닌 응답'

    assert run_pipeline(harness_db, 'https://official.example', fake_llm).status == Status.UNKNOWN


def test_vector_order_filter_and_limit(harness_db):
    assert search_similar_cases(harness_db, VECTOR, limit=1) == ['가상기관 인증 요구 사례']
    assert search_similar_cases(harness_db, VECTOR, limit=3) == ['가상기관 인증 요구 사례', '가상 택배 사례']


def test_no_cases_is_distinct_from_database_failure(harness_db):
    harness_db.session.execute(text('DELETE FROM cases'))
    assert search_similar_cases(harness_db, VECTOR) == []


def test_detail_search_applies_distance_filter_in_sql(harness_db):
    cases = search_case_details(harness_db, VECTOR, max_distance=0.3)
    assert [(case.id, case.distance) for case in cases] == [(3, 0.0)]
    assert [case.id for case in search_case_details(harness_db, VECTOR)] == [3, 4]


def test_unparsed_url_does_not_become_safe(harness_db):
    def must_not_call(*args):
        pytest.fail('URL 추출 실패를 확인한 뒤에는 정상 판정을 진행하면 안 됩니다')

    result = run_pipeline(harness_db, 'https://official.example https://notice.example:wrong', must_not_call)
    assert result.status == Status.UNKNOWN


@pytest.mark.parametrize('bad_url', ['https://notice.example:wrong', 'https://demo@official.example'])
def test_known_scam_phone_takes_priority_over_incomplete_url(harness_db, bad_url):
    harness_db.session.execute(text(
        "INSERT INTO entities VALUES ('01000000000', 'phone', 'scam')"
    ))

    def must_not_call(*args):
        pytest.fail('등록된 사기 번호가 있으면 LLM 없이 RISK여야 합니다')

    result = run_pipeline(harness_db, f'010-0000-0000 {bad_url}', must_not_call)
    assert result.status == Status.RISK


def test_userinfo_url_cannot_gain_official_match(harness_db):
    def must_not_call(*args):
        pytest.fail('추출 불완전 상태는 정상 판정으로 진행하면 안 됩니다')

    result = run_pipeline(harness_db, 'https://demo@official.example', must_not_call)
    assert result.status == Status.UNKNOWN
