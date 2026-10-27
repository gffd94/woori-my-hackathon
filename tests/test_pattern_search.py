"""활성 수법 카드 hybrid 검색(SPEC 2.7, 3.2.2 U-09~U-16). DB는 SQL 문구로 응답하는 대역을 쓴다."""

import pytest
from sqlalchemy.exc import OperationalError

from app.services.retriever import (
    NGRAM_THRESHOLD,
    VECTOR_THRESHOLD,
    ngram_similarity,
    rrf_merge,
    search_patterns,
    top_matches,
)


def query_vector():
    return [1.0] + [0.0] * 1535


class Result:
    def __init__(self, rows):
        self.rows = rows

    def mappings(self):
        return self

    def all(self):
        return self.rows

    def one(self):
        return self.rows[0]


class FakeDB:
    """patterns: {id: {"summary", "examples", "similarity"(벡터 유사도 또는 None), "active"}}"""

    def __init__(self, patterns, *, invalid=0, fail_on=None):
        self.patterns = patterns
        self.invalid = invalid
        self.fail_on = fail_on
        self.sql = []
        self.ngram_batches = 0

    def _active(self):
        return {pid: p for pid, p in sorted(self.patterns.items()) if p.get("active", True)}

    def execute(self, query, params=None):
        sql = str(query)
        self.sql.append(sql)
        if self.fail_on and self.fail_on in sql:
            raise OperationalError(sql, params, Exception("가상 DB 오류"))
        active = self._active()
        if "count(*)" in sql:
            filled = sum(1 for p in active.values() if p.get("similarity") is not None)
            return Result([{"total": len(active), "filled": filled, "invalid": self.invalid}])
        if "id > :after" in sql:
            self.ngram_batches += 1
            ids = [pid for pid in active if pid > params["after"]][: params["batch"]]
            return Result([
                {
                    "id": pid,
                    "summary": active[pid].get("summary"),
                    "example_messages": [{"text": t, "type": "sms"} for t in active[pid].get("examples", [])],
                }
                for pid in ids
            ])
        if "<=>" in sql:
            rows = sorted(
                ((pid, 1 - p["similarity"]) for pid, p in active.items() if p.get("similarity") is not None),
                key=lambda item: (item[1], item[0]),
            )[: params["limit"]]
            return Result([{"id": pid, "distance": distance} for pid, distance in rows])
        if "id IN" in sql:
            return Result([
                {
                    "id": pid,
                    "name": f"가상 수법 {pid}",
                    "summary": self.patterns[pid].get("summary"),
                    "example_messages": [{"text": t} for t in self.patterns[pid].get("examples", [])],
                }
                for pid in params["ids"]
            ])
        raise AssertionError(f"예상하지 못한 SQL: {sql}")

    def rollback(self):
        pass


MESSAGE = "[가상택배] 주소 불명으로 반송 예정입니다 주소를 확인해 주세요"


def test_U09_n_gram은_0_35_이상만_통과한다():
    assert NGRAM_THRESHOLD == 0.35
    picked = top_matches([(1, 0.3499), (2, 0.35), (3, 0.36)], NGRAM_THRESHOLD)
    assert [pid for pid, _ in picked] == [3, 2]


def test_U10_벡터는_0_43_이상만_통과한다():
    assert VECTOR_THRESHOLD == 0.43
    picked = top_matches([(1, 0.4299), (2, 0.43), (3, 0.44)], VECTOR_THRESHOLD)
    assert [pid for pid, _ in picked] == [3, 2]


def test_n_gram_유사도는_전처리_후_3글자_집합의_Jaccard다():
    assert ngram_similarity("주소 불명 반송", "주소불명반송") == 1.0
    assert ngram_similarity("ＡＢＣＤ", "abcd") == 1.0
    assert ngram_similarity("OOO님 주소 확인", "고객님 주소 확인") < 1.0
    assert ngram_similarity("OOO님 주소 확인", "님 주소 확인") == 1.0
    assert ngram_similarity("가나", "가나") == 0.0
    assert ngram_similarity("가나다라", "") == 0.0


def test_U11_활성_수법_카드만_검색하고_cases는_보지_않는다():
    db = FakeDB({
        1: {"summary": None, "examples": [MESSAGE], "similarity": 0.95},
        2: {"summary": None, "examples": [MESSAGE], "similarity": 0.95, "active": False},
    })
    result = search_patterns(db, MESSAGE, query_vector())

    assert result.status == "completed"
    assert [p.id for p in result.patterns] == [1]
    pattern_sql = [sql for sql in db.sql if "FROM patterns" in sql and "id IN" not in sql]
    assert pattern_sql and all("is_active" in sql for sql in pattern_sql)
    assert not any("cases" in sql for sql in db.sql)


def test_U12_두_방식에서_같은_카드는_한_번만_세고_RRF로_정렬한다():
    assert rrf_merge([1, 2], [2, 3]) == [2, 1, 3]


def test_U13_동점은_ID_오름차순이다():
    assert rrf_merge([5, 3], [3, 5]) == [3, 5]
    assert top_matches([(9, 0.9), (4, 0.9)], 0.5) == [(4, 0.9), (9, 0.9)]


def test_U14_LLM에는_최대_5개만_전달한다():
    assert rrf_merge([1, 2, 3, 4, 5], [6, 7, 8, 9, 10]) == [1, 6, 2, 7, 3]
    db = FakeDB({pid: {"examples": [MESSAGE], "similarity": 0.9} for pid in range(1, 9)})
    result = search_patterns(db, MESSAGE, query_vector())
    assert [p.id for p in result.patterns] == [1, 2, 3, 4, 5]
    assert result.matched_cases == 5
    assert result.patterns[0].examples == [MESSAGE]


def test_U15b_활성_카드_벡터가_빠지면_limited와_null이다():
    db = FakeDB({
        1: {"examples": [MESSAGE], "similarity": 0.95},
        2: {"examples": ["가상 문구"], "similarity": None},
    })
    result = search_patterns(db, MESSAGE, query_vector())

    assert (result.status, result.coverage, result.reason_code) == ("limited", "limited", "vector_missing")
    assert result.matched_cases is None


def test_U15b_저장된_벡터가_손상되면_limited다():
    db = FakeDB({1: {"examples": [MESSAGE], "similarity": 0.95}}, invalid=1)
    result = search_patterns(db, MESSAGE, query_vector())

    assert (result.status, result.reason_code) == ("limited", "vector_invalid")
    assert result.matched_cases is None


@pytest.mark.parametrize("fail_on", ["count(*)", "id > :after", "<=>", "id IN"])
def test_U15c_DB_오류는_failed와_unknown이다(fail_on):
    db = FakeDB({1: {"examples": [MESSAGE], "similarity": 0.95}}, fail_on=fail_on)
    result = search_patterns(db, MESSAGE, query_vector())

    assert (result.status, result.coverage, result.reason_code) == ("failed", "unknown", "db_error")
    assert result.matched_cases is None


def test_U16_배치_500을_넘는_오래된_카드도_찾는다():
    patterns = {pid: {"examples": [f"전혀 다른 가상 문구 {pid}"], "similarity": 0.1} for pid in range(1, 1201)}
    patterns[3] = {"examples": [MESSAGE], "similarity": 0.1}
    db = FakeDB(patterns)

    result = search_patterns(db, MESSAGE, query_vector())

    assert result.status == "completed"
    assert [p.id for p in result.patterns] == [3]
    assert db.ngram_batches == 3


def test_벡터만_가까운_카드도_찾는다():
    db = FakeDB({1: {"examples": ["전혀 다른 가상 문구"], "similarity": 0.85}})
    result = search_patterns(db, MESSAGE, query_vector())
    assert [p.id for p in result.patterns] == [1]


def test_일치가_없으면_completed_0이다():
    db = FakeDB({1: {"examples": ["전혀 다른 가상 문구"], "similarity": 0.3}})
    result = search_patterns(db, MESSAGE, query_vector())
    assert (result.status, result.coverage, result.matched_cases) == ("completed", "complete", 0)


def test_활성_카드가_0개면_completed_0이다():
    result = search_patterns(FakeDB({}), MESSAGE, query_vector())
    assert (result.status, result.method, result.matched_cases) == ("completed", "hybrid", 0)


def test_검색_예산_5초를_넘기면_limited다():
    ticks = iter([0.0, 0.1, 6.0, 6.0, 6.0, 6.0, 6.0])
    db = FakeDB({1: {"examples": [MESSAGE], "similarity": 0.95}})
    result = search_patterns(db, MESSAGE, query_vector(), clock=lambda: next(ticks))

    assert (result.status, result.coverage, result.reason_code) == ("limited", "limited", "time_budget")
    assert result.matched_cases is None


def test_질의_임베딩이_없으면_문자_전용_limited다():
    result = search_patterns(FakeDB({1: {"examples": [MESSAGE], "similarity": 0.9}}), MESSAGE, None)
    assert (result.status, result.method, result.reason_code) == ("limited", "ngram", "text_only")
    assert result.matched_cases is None


def test_질의_임베딩이_잘못되면_failed다():
    result = search_patterns(FakeDB({}), MESSAGE, [0.0] * 1536)
    assert (result.status, result.coverage, result.reason_code) == ("failed", "unknown", "embedding_invalid")
