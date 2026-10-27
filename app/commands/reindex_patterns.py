"""벡터가 NULL인 활성 수법 카드의 임베딩을 생성한다(SPEC 2.8.3).

    python -m app.commands.reindex_patterns            # 실제 임베딩 API 호출
    python -m app.commands.reindex_patterns --dry-run  # 대상만 출력, 외부 호출 없음

외부 호출 중에는 DB 행 잠금이나 트랜잭션을 유지하지 않는다. 저장 직전에 카드를 다시 읽어
호출 중 내용이 바뀌었거나 이미 벡터가 채워졌으면 저장하지 않는다.
생성에 실패한 카드의 벡터는 바꾸지 않는다.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Protocol

from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from app.services.embedding import EmbeddingError, embed_texts, pattern_embedding_text

BATCH_SIZE = 50

_CARD_COLUMNS = "id, name, summary, impersonation, lure_action, triggers, example_messages"


@dataclass(frozen=True)
class PendingPattern:
    id: int
    text: str


@dataclass
class ReindexResult:
    updated: int = 0
    skipped: int = 0
    failed: int = 0
    failed_ids: list[int] = field(default_factory=list)


class PatternStore(Protocol):
    def pending(self) -> list[PendingPattern]: ...

    def save(self, row: PendingPattern, embedding: list[float]) -> bool: ...


class SqlPatternStore:
    """PostgreSQL patterns 테이블. 조회와 저장을 각각 짧은 트랜잭션으로 처리한다."""

    def __init__(self, session_factory: sessionmaker[Session]):
        self.session_factory = session_factory

    def pending(self) -> list[PendingPattern]:
        with self.session_factory() as session:
            rows = session.execute(text(
                f"SELECT {_CARD_COLUMNS} FROM patterns "
                "WHERE is_active AND embedding IS NULL ORDER BY id"
            )).mappings().all()
        return [PendingPattern(id=row["id"], text=pattern_embedding_text(row)) for row in rows]

    def save(self, row: PendingPattern, embedding: list[float]) -> bool:
        vector = "[" + ",".join(repr(value) for value in embedding) + "]"
        with self.session_factory() as session, session.begin():
            current = session.execute(
                text(
                    f"SELECT {_CARD_COLUMNS} FROM patterns "
                    "WHERE id = :id AND is_active AND embedding IS NULL FOR UPDATE"
                ),
                {"id": row.id},
            ).mappings().first()
            if current is None or pattern_embedding_text(current) != row.text:
                return False
            session.execute(
                text("UPDATE patterns SET embedding = CAST(:embedding AS vector) WHERE id = :id"),
                {"id": row.id, "embedding": vector},
            )
        return True


def reindex_patterns(
    store: PatternStore,
    embed: Callable[[list[str]], list[list[float]]],
    *,
    batch_size: int = BATCH_SIZE,
) -> ReindexResult:
    result = ReindexResult()
    rows = store.pending()
    for start in range(0, len(rows), batch_size):
        batch = rows[start:start + batch_size]
        try:
            vectors = embed([row.text for row in batch])
        except EmbeddingError:
            result.failed += len(batch)
            result.failed_ids.extend(row.id for row in batch)
            continue
        for row, vector in zip(batch, vectors, strict=True):
            if store.save(row, vector):
                result.updated += 1
            else:
                result.skipped += 1
    return result


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="활성 수법 카드 임베딩 재색인")
    parser.add_argument("--dry-run", action="store_true", help="대상만 출력하고 외부 API를 호출하지 않음")
    args = parser.parse_args(argv)

    from app.db.session import get_session_factory

    store = SqlPatternStore(get_session_factory())
    if args.dry_run:
        rows = store.pending()
        print(f"재색인 대상 {len(rows)}개, 총 {sum(len(r.text) for r in rows)}자")
        for row in rows:
            print(f"- #{row.id} {row.text.splitlines()[0]} ({len(row.text)}자)")
        return 0

    result = reindex_patterns(store, lambda texts: embed_texts(texts))
    print(f"저장 {result.updated}개, 건너뜀 {result.skipped}개, 실패 {result.failed}개")
    if result.failed_ids:
        print("실패한 수법 카드 ID: " + ", ".join(map(str, result.failed_ids)))
    return 1 if result.failed else 0


if __name__ == "__main__":
    sys.exit(main())
