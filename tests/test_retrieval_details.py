import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.services.extractor import extract, normalize_url, normalize_domain
from app.services.retriever import (
    ExtractionIncompleteError, lookup_entities, lookup_entity_details,
    search_case_details, build_entity_lookup,
)


def test_shared_url_normalization():
    assert normalize_url('https://NOTICE.example:443/') == 'https://notice.example'
    assert normalize_url('http://NOTICE.example:80/Check?q=AbC!') == 'http://notice.example/Check?q=AbC!'
    assert normalize_domain('NOTICE.example.') == 'notice.example'
    assert normalize_url('https://notice.example:8443/Check') == 'https://notice.example:8443/Check'


def test_bad_url_is_visible_and_prevents_normal_lookup():
    result = extract('https://notice.example:wrong')
    assert result.unparsed_urls == ['https://notice.example:wrong']
    assert result.warnings
    with pytest.raises(ExtractionIncompleteError):
        lookup_entities(None, result)
    with pytest.raises(ExtractionIncompleteError):
        build_entity_lookup(result, [])


def test_query_punctuation_is_not_silently_changed():
    assert extract('https://notice.example/?token=AbC!').urls == ['https://notice.example?token=AbC!']


def test_source_is_available_without_changing_entity_match():
    engine = create_engine('sqlite://')
    with Session(engine) as db:
        db.execute(text('CREATE TABLE entities (value TEXT, type TEXT, label TEXT, source TEXT)'))
        db.execute(text("INSERT INTO entities VALUES ('notice.example', 'domain', 'official', '가상기관 제공')"))
        result = lookup_entity_details(db, extract('https://notice.example'))
        assert result[0].source == '가상기관 제공'
        assert result[0].as_match().label == 'official'
    engine.dispose()


class DetailDB:
    def execute(self, query, params):
        self.sql, self.params = str(query), params
        return self

    def mappings(self):
        return self

    def __iter__(self):
        return iter([{'id': 7, 'message_text': '가상기관 사칭', 'distance': 0.12}])


def test_case_details_include_distance_and_id():
    db = DetailDB()
    cases = search_case_details(db, [0.1] * 1536, max_distance=0.3)
    assert cases[0].id == 7
    assert cases[0].distance == 0.12
    assert db.params['max_distance'] == 0.3
    assert '<= :max_distance' in db.sql


@pytest.mark.parametrize('distance', [-0.1, 2.1, float('nan'), True, '0.3'])
def test_invalid_distance_rejected(distance):
    with pytest.raises(ValueError):
        search_case_details(None, [0.1] * 1536, max_distance=distance)
