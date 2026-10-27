"""수법 카드 재색인(SPEC 2.8.3). 저장소와 임베딩 호출은 대역을 쓴다."""

from app.commands.reindex_patterns import PendingPattern, reindex_patterns
from app.services.embedding import EmbeddingError


def vector(first=0.1):
    return [first] + [0.01] * 1535


class FakeStore:
    def __init__(self, rows, changed_ids=()):
        self.rows = rows
        self.changed_ids = set(changed_ids)
        self.saved = {}

    def pending(self):
        return list(self.rows)

    def save(self, row, embedding):
        # 외부 호출 중 내용이 바뀐 카드는 저장하지 않는다.
        if row.id in self.changed_ids:
            return False
        self.saved[row.id] = embedding
        return True


def row(pattern_id, name):
    return PendingPattern(id=pattern_id, text=f"수법: {name}")


def test_벡터가_없는_활성_카드를_배치로_임베딩해_저장한다():
    store = FakeStore([row(1, "가상 A"), row(2, "가상 B"), row(3, "가상 C")])
    calls = []

    def embed(texts):
        calls.append(list(texts))
        return [vector(0.1 * (i + 1)) for i in range(len(texts))]

    result = reindex_patterns(store, embed, batch_size=2)

    assert calls == [["수법: 가상 A", "수법: 가상 B"], ["수법: 가상 C"]]
    assert set(store.saved) == {1, 2, 3}
    assert (result.updated, result.skipped, result.failed) == (3, 0, 0)


def test_생성에_실패한_배치는_벡터를_바꾸지_않고_나머지는_계속한다():
    store = FakeStore([row(1, "가상 A"), row(2, "가상 B")])

    def embed(texts):
        if texts == ["수법: 가상 A"]:
            raise EmbeddingError("가상 실패")
        return [vector()]

    result = reindex_patterns(store, embed, batch_size=1)

    assert set(store.saved) == {2}
    assert (result.updated, result.skipped, result.failed) == (1, 0, 1)
    assert result.failed_ids == [1]


def test_호출_중_내용이_바뀐_카드는_건너뛴다():
    store = FakeStore([row(1, "가상 A"), row(2, "가상 B")], changed_ids={2})

    result = reindex_patterns(store, lambda texts: [vector() for _ in texts], batch_size=10)

    assert set(store.saved) == {1}
    assert (result.updated, result.skipped, result.failed) == (1, 1, 0)


def test_대상이_없으면_임베딩을_호출하지_않는다():
    def embed(texts):
        raise AssertionError("호출되면 안 됨")

    result = reindex_patterns(FakeStore([]), embed)

    assert (result.updated, result.skipped, result.failed) == (0, 0, 0)
