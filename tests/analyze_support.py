"""POST /analyze 테스트용 대역과 실제 호출 차단 장치 (SPEC 3.1.3, 3.7.2).

합성 도메인(official.example 등)과 가상 값만 쓴다.
"""

import http.client
import socket
import urllib.request
from dataclasses import dataclass, field

import psycopg
import pytest

import app.db.session as db_session
from app.services.analyzer import (
    Analyzer,
    IndicatorMatch,
    LookupResult,
    PatternCard,
    SearchOutcome,
    VerdictRecord,
)
from app.services.llm_judge import LLMJudgement

VECTOR = [0.01] * 1536
CARD_1 = PatternCard(id=1, name="가상 택배 조회 사칭", summary="택배 조회를 핑계로 URL 접속 유도",
                     impersonation="택배사", lure_action="URL 클릭", triggers=("택배", "반송"))
CARD_2 = PatternCard(id=2, name="가상 기관 과태료 사칭", summary="과태료 조회 유도")
COMPLETED = SearchOutcome(status="completed", method="hybrid", coverage="complete", patterns=(CARD_1, CARD_2))

SAFE_LLM = LLMJudgement(is_high_risk=False, signals=[], reasons=[], suggestion="SAFE")
RISK_LLM = LLMJudgement(is_high_risk=True, signals=["기관 사칭", "비공식 URL"], reasons=["근거"], suggestion="RISK")
UNKNOWN_LLM = LLMJudgement(is_high_risk=False, signals=[], reasons=[], suggestion="UNKNOWN")


@dataclass
class Fakes:
    """호출 인자를 기록하는 대역. 요청마다 새로 만들어 상태가 새지 않게 한다."""

    lookup_result: LookupResult = field(default_factory=LookupResult)
    vector: list[float] = field(default_factory=lambda: list(VECTOR))
    outcome: SearchOutcome = COMPLETED
    judgement: LLMJudgement | None = field(default_factory=lambda: SAFE_LLM)
    fail: set[str] = field(default_factory=set)
    calls: dict[str, list] = field(default_factory=lambda: {
        "lookup": [], "embed": [], "search": [], "judge": [], "save": []
    })

    def _maybe_fail(self, stage):
        if stage in self.fail:
            raise RuntimeError(f"{stage} 대역 실패 SECRET-TEST-VALUE 원문:주민 900101-1234567")

    def lookup(self, extracted):
        self.calls["lookup"].append(extracted)
        self._maybe_fail("lookup")
        return self.lookup_result

    def embed(self, text):
        self.calls["embed"].append(text)
        self._maybe_fail("embed")
        return self.vector

    def search(self, text, vector):
        self.calls["search"].append((text, vector))
        self._maybe_fail("search")
        return self.outcome

    def judge(self, message, cards, entity_lookup):
        self.calls["judge"].append((message, cards, entity_lookup))
        self._maybe_fail("judge")
        return self.judgement

    def save(self, record: VerdictRecord):
        self.calls["save"].append(record)
        self._maybe_fail("save")

    def analyzer(self, model_version="test-llm-model"):
        return Analyzer(lookup=self.lookup, embed=self.embed, search=self.search,
                        judge=self.judge, save=self.save, model_version=model_version)


def official(*domains):
    return LookupResult(official_domains=frozenset(domains))


def malicious(*matches):
    return LookupResult(indicators=tuple(IndicatorMatch(i, t, v) for i, (t, v) in enumerate(matches, 1)))


@pytest.fixture
def block_real_calls(monkeypatch):
    """실제 DB 연결·외부 HTTP를 시도하면 기록하고 즉시 실패시킨다.

    TestClient의 인메모리 ASGI 요청은 소켓을 쓰지 않으므로 영향이 없다.
    """
    attempts = []

    def blocked(name):
        def _raise(*args, **kwargs):
            attempts.append(name)
            raise AssertionError(f"테스트 중 실제 호출 시도 차단: {name}")
        return _raise

    monkeypatch.setattr(socket, "create_connection", blocked("socket.create_connection"))
    monkeypatch.setattr(http.client.HTTPConnection, "connect", blocked("http.connect"))
    monkeypatch.setattr(urllib.request, "urlopen", blocked("urllib.urlopen"))
    monkeypatch.setattr(psycopg.Connection, "connect", classmethod(blocked("psycopg.connect")))
    monkeypatch.setattr(db_session, "get_engine", blocked("db_session.get_engine"))
    yield attempts
