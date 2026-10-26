"""첨부 검토에서 지적한 URL 사용자 정보와 함수 호환성 회귀 테스트."""

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.services.extractor import extract, extract_entities, normalize_url
from app.services.retriever import ExtractionIncompleteError, lookup_entities


def test_userinfo_is_removed_from_lookup_url_but_not_silently_accepted():
    message = 'https://official.example@evil.test/login'
    result = extract_entities(message)
    assert result.urls == ['https://evil.test/login']
    assert result.domains == ['evil.test']
    assert result.has_userinfo is True
    assert result.unparsed_urls == [message]
    assert result.warnings
    engine = create_engine('sqlite://')
    with Session(engine) as db:
        db.execute(text('CREATE TABLE entities (value TEXT, type TEXT, label TEXT)'))
        with pytest.raises(ExtractionIncompleteError):
            lookup_entities(db, result)
    engine.dispose()


def test_normalize_url_drops_credentials_and_preserves_destination():
    assert normalize_url('https://demo:dummy@NOTICE.example:8443/Check?q=AbC') == (
        'https://notice.example:8443/Check?q=AbC'
    )


def test_old_and_new_function_names_are_compatible():
    message = '가상은행 https://notice.example 안내 010-0000-0000'
    assert extract(message, ['가상은행']) == extract_entities(message, ['가상은행'])
    assert not extract_entities(message).has_userinfo


def test_query_punctuation_is_preserved():
    assert extract_entities('https://notice.example/check?id=123.').urls == [
        'https://notice.example/check?id=123.'
    ]
