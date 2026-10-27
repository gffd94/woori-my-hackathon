"""DB 설정과 요청 단위 세션의 트랜잭션 경계를 검증한다."""

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import QueuePool

import app.config as config

_real_load_dotenv = config.load_dotenv


def _use_dotenv(monkeypatch, dotenv_file):
    # load_dotenv()는 작업 위치가 아니라 config.py 위치부터 .env를 찾으므로 경로를 직접 지정한다
    monkeypatch.setattr(
        config,
        "load_dotenv",
        lambda override: _real_load_dotenv(dotenv_path=dotenv_file, override=override),
    )


def _unset_env(monkeypatch, name):
    # load_dotenv가 os.environ에 써 넣은 값도 테스트 후 원래대로 되돌리도록 기록해 둔다
    monkeypatch.setenv(name, "")
    monkeypatch.delenv(name)


@pytest.fixture(autouse=True)
def isolate_dotenv(tmp_path, monkeypatch):
    """프로젝트의 실제 .env 대신 빈 임시 .env를 읽게 한다."""
    empty = tmp_path / "empty.env"
    empty.write_text("", encoding="utf-8")
    _use_dotenv(monkeypatch, empty)


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
        _unset_env(monkeypatch, "DATABASE_URL")
    else:
        monkeypatch.setenv("DATABASE_URL", database_url)
    get_engine.cache_clear()
    try:
        with pytest.raises(RuntimeError, match="DATABASE_URL"):
            get_engine()
    finally:
        get_engine.cache_clear()


def test_DATABASE_URL이_env파일에만_있으면_그_주소로_엔진을_만든다(tmp_path, monkeypatch):
    from app.db.session import get_engine

    dotenv_file = tmp_path / ".env"
    dotenv_file.write_text("DATABASE_URL=postgresql+psycopg://localhost/dotenv_only\n", encoding="utf-8")
    _use_dotenv(monkeypatch, dotenv_file)
    _unset_env(monkeypatch, "DATABASE_URL")
    get_engine.cache_clear()
    engine = get_engine()
    try:
        assert engine.url.database == "dotenv_only"
        assert engine.pool.checkedout() == 0
    finally:
        engine.dispose()
        get_engine.cache_clear()


def test_환경변수와_env파일에_모두_있으면_환경변수가_우선한다(tmp_path, monkeypatch):
    from app.db.session import get_engine

    dotenv_file = tmp_path / ".env"
    dotenv_file.write_text("DATABASE_URL=postgresql+psycopg://localhost/from_dotenv\n", encoding="utf-8")
    _use_dotenv(monkeypatch, dotenv_file)
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://localhost/from_environment")
    get_engine.cache_clear()
    engine = get_engine()
    try:
        assert engine.url.database == "from_environment"
    finally:
        engine.dispose()
        get_engine.cache_clear()
