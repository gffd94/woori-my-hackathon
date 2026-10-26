"""전용 테스트 DB 주소가 있을 때만 실제 PostgreSQL·pgvector SQL을 검증한다."""

import os

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.services.extractor import extract
from app.services.retriever import lookup_entities, search_similar_cases, search_case_details


@pytest.mark.skipif(not os.environ.get('HARNESS_DATABASE_URL'), reason='전용 pgvector 테스트 DB 미설정')
def test_real_pgvector_lookup_and_search():
    # 드라이버와 vector 확장은 DB 담당자가 미리 준비한다. 확장을 자동 설치하지 않는다.
    engine = create_engine(os.environ['HARNESS_DATABASE_URL'])
    try:
        with engine.connect() as connection:
            transaction = connection.begin()
            try:
                connection.execute(text(
                    'CREATE TEMP TABLE entities (value TEXT, type TEXT, label TEXT) ON COMMIT DROP'
                ))
                connection.execute(text(
                    'CREATE TEMP TABLE cases (id INTEGER, message_text TEXT, status TEXT, '
                    'embedding vector(1536)) ON COMMIT DROP'
                ))
                connection.execute(text(
                    "INSERT INTO pg_temp.entities VALUES ('official.example', 'domain', 'official')"
                ))
                near = [1.0] + [0.0] * 1535
                far = [0.0, 1.0] + [0.0] * 1534
                for case_id, message, status, vector in [
                    (1, '미검증 사례', 'pending', near),
                    (2, '반려 사례', 'rejected', near),
                    (3, '검증된 가까운 사례', 'verified', near),
                    (4, '검증된 먼 사례', 'verified', far),
                    (5, '영벡터 사례', 'verified', [0.0] * 1536),
                ]:
                    connection.execute(text(
                        'INSERT INTO pg_temp.cases VALUES (:id, :message, :status, CAST(:vector AS vector))'
                    ), dict(id=case_id, message=message, status=status,
                            vector='[' + ','.join(map(str, vector)) + ']'))
                with Session(bind=connection, join_transaction_mode='create_savepoint') as db:
                    matches = lookup_entities(db, extract('https://official.example'))
                    assert [(m.value, m.label) for m in matches] == [('official.example', 'official')]
                    assert search_similar_cases(db, near, limit=1) == ['검증된 가까운 사례']
                    assert search_similar_cases(db, near) == ['검증된 가까운 사례', '검증된 먼 사례']
                    details = search_case_details(db, near, max_distance=0.3)
                    assert [case.id for case in details] == [3]
                    assert details[0].distance == pytest.approx(0.0)
            finally:
                # 임시 테이블과 테스트 데이터는 성공·실패 모두 롤백한다.
                transaction.rollback()
    finally:
        engine.dispose()
