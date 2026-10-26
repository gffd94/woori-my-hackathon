import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.services.decision import Status, check_blacklist
from app.services.extractor import extract
from app.services.retriever import build_entity_lookup, lookup_entities, search_similar_cases


def test_lookup_matches_exact_value_and_type_and_connects_to_decision():
    engine = create_engine('sqlite://')
    with Session(engine) as db:
        db.execute(text('CREATE TABLE entities (value TEXT, type TEXT, label TEXT)'))
        db.execute(text("INSERT INTO entities VALUES "
                        "('bank.example', 'domain', 'official'), "
                        "('bad.example', 'domain', 'scam'), "
                        "('01000000000', 'url', 'official')"))
        extracted = extract('https://bank.example.evil.test https://bad.example 010-0000-0000')
        matches = lookup_entities(db, extracted)
        assert [(m.value, m.label) for m in matches] == [('bad.example', 'scam')]
        assert check_blacklist(matches).status == Status.RISK
        lookup = build_entity_lookup(extracted, matches)
        assert lookup['bad.example'] == 'scam'
        assert lookup['bank.example.evil.test'] is None
        assert lookup['01000000000'] is None
    engine.dispose()


def test_database_failure_is_not_treated_as_no_matches():
    engine = create_engine('sqlite://')
    with Session(engine) as db:
        with pytest.raises(Exception):
            lookup_entities(db, extract('https://notice.example'))
    engine.dispose()


class SearchDB:
    def execute(self, query, parameters):
        self.sql = str(query)
        self.parameters = parameters
        return self

    def scalars(self):
        return self

    def all(self):
        return ['가상기관 사칭 사례']


def test_vector_search_returns_llm_case_texts_and_only_verified():
    db = SearchDB()
    cases = search_similar_cases(db, [0.1] * 1536, limit=3)
    assert cases == ['가상기관 사칭 사례']
    assert "status = 'verified'" in db.sql
    assert db.parameters['limit'] == 3
    assert db.parameters['embedding'].startswith('[0.1,')


@pytest.mark.parametrize('embedding', [[], [0.1], [float('nan')] * 1536, [float('inf')] * 1536, [0.0] * 1536])
def test_invalid_vector_is_rejected(embedding):
    with pytest.raises(ValueError):
        search_similar_cases(SearchDB(), embedding)


def test_invalid_limit_is_rejected():
    with pytest.raises(ValueError):
        search_similar_cases(SearchDB(), [0.1] * 1536, limit=0)
