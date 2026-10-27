"""analyzer 호출 경계의 실제 DB 구현(lookup·search·save). DB는 SQL 문구로 응답하는 대역을 쓴다."""

import pytest
from sqlalchemy.exc import OperationalError

from app.services.analyzer import IndicatorMatch, PatternCard, VerdictRecord
from app.services.extractor import ExtractedEntities
from app.services.repository import lookup_indicators, save_verdict, search_cards
from app.services.retriever import PatternMatch, PatternRetrieval


class Result:
    def __init__(self, rows):
        self.rows = rows

    def mappings(self):
        return self

    def all(self):
        return self.rows


class FakeSession:
    def __init__(self, *, indicators=(), official=(), fail=False):
        self.indicators = indicators  # (id, type, value)
        self.official = official
        self.fail = fail
        self.calls = []
        self.committed = self.rolled_back = self.closed = False

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.closed = True

    def execute(self, query, params=None):
        sql = str(query)
        self.calls.append((sql, params))
        if self.fail:
            raise OperationalError(sql, params, Exception("가상 DB 오류"))
        if "FROM indicators" in sql:
            return Result([
                {"id": i, "type": t, "value_normalized": v}
                for i, t, v in self.indicators
                if t == params["type"] and v in params["values"]
            ])
        if "FROM official_links" in sql:
            return Result([{"domain": d} for d in self.official if d in params["domains"]])
        return Result([])

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True


def extracted(urls=(), domains=(), phones=()):
    return ExtractedEntities(urls=list(urls), domains=list(domains), phones=list(phones))


RECORD = VerdictRecord(
    message_masked="가상 문자 [전화번호]",
    verdict="RISK",
    score=None,
    matched_pattern_ids=(3, 1),
    matched_indicator_ids=(7,),
    reasoning="가상 근거",
    model_version="가상-모델",
)


# --- lookup ---

def test_추출_값이_없으면_DB를_조회하지_않는다():
    session = FakeSession()

    result = lookup_indicators(extracted(), session_factory=lambda: session)

    assert result.indicators == () and result.official_domains == frozenset()
    assert session.calls == []


def test_유형별로_정확히_같은_값만_악성_일치로_돌려준다():
    session = FakeSession(indicators=[
        (1, "url", "https://bad.example/a"),
        (2, "domain", "bad.example"),
        (3, "phone", "01000000000"),
        (4, "domain", "https://bad.example/a"),  # 유형이 다르면 일치가 아니다
    ])

    result = lookup_indicators(
        extracted(urls=["https://bad.example/a"], domains=["bad.example"], phones=["01000000000"]),
        session_factory=lambda: session,
    )

    assert set(result.indicators) == {
        IndicatorMatch(1, "url", "https://bad.example/a"),
        IndicatorMatch(2, "domain", "bad.example"),
        IndicatorMatch(3, "phone", "01000000000"),
    }
    assert session.closed and not session.committed


def test_공식_도메인은_호스트가_정확히_같을_때만_돌려준다():
    session = FakeSession(official=["bank.example"])

    result = lookup_indicators(
        extracted(urls=["https://www.bank.example"], domains=["www.bank.example", "bank.example"]),
        session_factory=lambda: session,
    )

    assert result.official_domains == frozenset({"bank.example"})


def test_대조_중_DB_오류는_호출자에게_올려_보낸다():
    session = FakeSession(fail=True)

    with pytest.raises(OperationalError):
        lookup_indicators(extracted(domains=["bad.example"]), session_factory=lambda: session)
    assert session.closed


# --- search ---

def test_완료된_검색은_수법_카드로_옮긴다(monkeypatch):
    session = FakeSession()
    seen = {}

    def fake_search(db, message, embedding):
        seen.update(db=db, message=message, embedding=embedding)
        return PatternRetrieval("completed", "hybrid", "complete", patterns=[
            PatternMatch(id=3, name="가상 수법 3", summary="요약", examples=["예시"], score=0.03),
        ])

    monkeypatch.setattr("app.services.repository.search_patterns", fake_search)

    outcome = search_cards("마스킹 문자", [0.1] * 1536, session_factory=lambda: session)

    assert outcome.status == "completed" and outcome.method == "hybrid" and outcome.coverage == "complete"
    assert outcome.patterns == (PatternCard(id=3, name="가상 수법 3", summary="요약"),)
    assert seen["db"] is session and seen["message"] == "마스킹 문자"
    assert session.closed


@pytest.mark.parametrize("retrieval", [
    PatternRetrieval("limited", "hybrid", "limited", "vector_missing"),
    PatternRetrieval("failed", "hybrid", "unknown", "db_error"),
])
def test_미완료_검색은_카드를_넘기지_않는다(monkeypatch, retrieval):
    monkeypatch.setattr("app.services.repository.search_patterns", lambda db, m, e: retrieval)

    outcome = search_cards("마스킹 문자", [0.1] * 1536, session_factory=FakeSession)

    assert (outcome.status, outcome.method, outcome.coverage) == (
        retrieval.status, retrieval.method, retrieval.coverage
    )
    assert outcome.patterns == ()


# --- save ---

def test_판정_기록을_INSERT하고_commit한다():
    session = FakeSession()

    save_verdict(RECORD, session_factory=lambda: session)

    sql, params = session.calls[0]
    assert "INSERT INTO verdict_logs" in sql
    assert params == {
        "message_masked": "가상 문자 [전화번호]",
        "verdict": "RISK",
        "score": None,
        "matched_pattern_ids": [3, 1],
        "matched_indicator_ids": [7],
        "reasoning": "가상 근거",
        "model_version": "가상-모델",
    }
    assert session.committed and session.closed


def test_기록_실패는_rollback하고_예외를_올려_보낸다():
    session = FakeSession(fail=True)

    with pytest.raises(OperationalError):
        save_verdict(RECORD, session_factory=lambda: session)
    assert session.rolled_back and not session.committed and session.closed
