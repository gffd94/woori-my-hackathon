"""DB 설정과 요청 단위 세션의 트랜잭션 경계를 검증한다."""

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import QueuePool


@pytest.mark.parametrize(
    "database_url",
    ["postgresql://localhost/smishing_test", "postgresql+psycopg://localhost/smishing_test"],
)
def test_환경변수의_PostgreSQL_주소로_엔진만_생성하고_아직_접속하지_않는다(
    monkeypatch, database_url
):
    from app.db.session import get_engine

    monkeypatch.setenv("DATABASE_URL", database_url)
    get_engine.cache_clear()
    engine = get_engine()
    try:
        assert engine.url.drivername == "postgresql+psycopg"
        assert engine.url.database == "smishing_test"
        assert engine.pool.checkedout() == 0
        assert get_engine() is engine
    finally:
        engine.dispose()
        get_engine.cache_clear()


@pytest.mark.parametrize("finish", ["normal", "error", "cancelled", "commit"])
def test_요청종료시_연결을_반환하고_명시적으로_커밋한_변경만_남긴다(tmp_path, finish):
    from app.db.session import get_db

    # 세션 수명은 SQLite로 검증한다. PostgreSQL 전용 모델의 적재 검증은 아니다.
    engine = create_engine(f"sqlite:///{(tmp_path / 'session-test.db').as_posix()}", poolclass=QueuePool)
    factory = sessionmaker(bind=engine)
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE session_probe (id INTEGER PRIMARY KEY)"))

    dependency = get_db(factory)
    session = next(dependency)
    try:
        session.execute(text("INSERT INTO session_probe (id) VALUES (1)"))
        assert engine.pool.checkedout() == 1
        if finish == "commit":
            session.commit()
        if finish == "error":
            with pytest.raises(RuntimeError, match="판정 중 오류"):
                dependency.throw(RuntimeError("판정 중 오류"))
        elif finish == "cancelled":
            dependency.close()
        else:
            with pytest.raises(StopIteration):
                next(dependency)

        assert engine.pool.checkedout() == 0
        with factory() as another_session:
            rows = another_session.execute(text("SELECT id FROM session_probe")).scalars().all()
        assert rows == ([1] if finish == "commit" else [])
    finally:
        dependency.close()
        engine.dispose()


@pytest.mark.parametrize(
    "database_url", [None, "", "   ", "잘못된 주소", "sqlite://", "postgresql+asyncpg://localhost/test"]
)
def test_DB설정이_없거나_지원하지_않는_주소면_접속전에_명확히_실패한다(monkeypatch, database_url):
    from app.db.session import get_engine

    if database_url is None:
        monkeypatch.delenv("DATABASE_URL", raising=False)
    else:
        monkeypatch.setenv("DATABASE_URL", database_url)
    get_engine.cache_clear()
    try:
        with pytest.raises(RuntimeError, match="DATABASE_URL"):
            get_engine()
    finally:
        get_engine.cache_clear()
