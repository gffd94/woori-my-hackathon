"""환경 변수로 설정하는 동기 SQLAlchemy 연결.

DATABASE_URL은 프로세스 환경 변수로 전달한다. 이 모듈을 가져오는 것만으로는
DB에 접속하지 않으며, 테이블 생성이나 vector 확장 설치도 수행하지 않는다.
"""

import os
from collections.abc import Iterator
from functools import lru_cache
from typing import Annotated

from fastapi import Depends
from sqlalchemy import Engine, create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError
from sqlalchemy.orm import Session, sessionmaker


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    """첫 사용 시 엔진을 만들고, 실제 연결은 쿼리 실행까지 미룬다."""
    database_url = os.getenv("DATABASE_URL", "").strip()
    if not database_url:
        raise RuntimeError("DATABASE_URL 환경 변수를 설정해야 합니다.")
    try:
        url = make_url(database_url)
    except (ArgumentError, ValueError):
        # 연결 문자열의 인증 정보가 예외 메시지에 노출되지 않도록 한다.
        raise RuntimeError("DATABASE_URL 형식이 올바르지 않습니다.") from None
    if url.drivername not in {"postgresql", "postgresql+psycopg"}:
        raise RuntimeError("DATABASE_URL은 postgresql+psycopg:// 형식을 사용해야 합니다.")
    return create_engine(
        url.set(drivername="postgresql+psycopg"),
        pool_pre_ping=True,
        hide_parameters=True,
    )


@lru_cache(maxsize=1)
def get_session_factory() -> sessionmaker[Session]:
    """세션 생성기는 공유하고, 세션 객체는 요청마다 새로 만든다."""
    return sessionmaker(bind=get_engine(), autoflush=False, expire_on_commit=False)


def get_db(
    factory: Annotated[sessionmaker[Session], Depends(get_session_factory)],
) -> Iterator[Session]:
    """FastAPI에서 Depends(get_db)로 사용한다.

    저장 호출자가 명시적으로 commit()해야 한다. 오류 시 rollback()하고,
    정상 종료·오류·요청 취소 모두 연결을 반환한다. 동기 DB 세션이므로
    비동기 경로에서 이벤트 루프를 막지 않도록 호출 방식을 맞춰야 한다.
    """
    with factory() as session:
        try:
            yield session
        except Exception:
            session.rollback()
            raise
