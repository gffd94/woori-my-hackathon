"""선택 실행하는 오류 처리 테스트의 DB·외부 전송 차단 플러그인."""

import importlib.abc
import socket
import sqlite3
import threading
import urllib.request

import dotenv
import httpx
import pytest
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.orm import Session


class _DatabaseImportBlocker(importlib.abc.MetaPathFinder):
    def __init__(self, attempts):
        self.attempts = attempts

    def find_spec(self, fullname, path=None, target=None):
        if fullname.split(".")[0] in {"psycopg", "psycopg2", "asyncpg"} or (
            fullname == "app.db" or fullname.startswith("app.db.")
        ):
            self.attempts.append("DB 모듈 접근")
            raise AssertionError("이 테스트에서는 DB 모듈을 사용할 수 없습니다.")
        return None


def pytest_configure(config):
    import os
    import sys

    patch = pytest.MonkeyPatch()
    attempts = []
    local = threading.local()

    def blocked(kind):
        def reject(*args, **kwargs):
            attempts.append(kind)
            raise AssertionError("실제 DB·외부 호출이 차단되었습니다.")

        return reject

    # 이벤트 루프의 자체 깨우기용 socketpair만 허용한다.
    original_socketpair = socket.socketpair

    def internal_socketpair(*args, **kwargs):
        previous = getattr(local, "socketpair", False)
        local.socketpair = True
        try:
            return original_socketpair(*args, **kwargs)
        finally:
            local.socketpair = previous

    def network_guard(original):
        def guarded(*args, **kwargs):
            if getattr(local, "socketpair", False):
                return original(*args, **kwargs)
            return blocked("네트워크 접근")(*args, **kwargs)

        return guarded

    patch.setattr(socket, "socketpair", internal_socketpair)
    for owner, names in (
        (socket, ("create_connection", "getaddrinfo", "gethostbyname", "gethostbyname_ex", "gethostbyaddr")),
        (socket.socket, ("connect", "connect_ex", "sendto")),
    ):
        for name in names:
            patch.setattr(owner, name, network_guard(getattr(owner, name)))

    patch.setattr(urllib.request, "urlopen", blocked("HTTP 전송"))
    patch.setattr(httpx.HTTPTransport, "handle_request", blocked("HTTP 전송"))
    patch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", blocked("HTTP 전송"))
    patch.setattr(sqlite3, "connect", blocked("SQLite 연결"))
    patch.setattr(sqlite3.dbapi2, "connect", blocked("SQLite 연결"))
    for owner, names in (
        (Engine, ("connect", "raw_connection")),
        (Connection, ("execute", "exec_driver_sql")),
        (Session, ("execute",)),
    ):
        for name in names:
            patch.setattr(owner, name, blocked("DB 연결·SQL 실행"))

    for name in tuple(os.environ):
        if name in {"DATABASE_URL", "TEST_DATABASE_URL", "HARNESS_DATABASE_URL", "ADMIN_API_KEY", "REPORT_FINGERPRINT_KEY"} or name.startswith(("LLM_", "EMBEDDING_", "OPENAI_")):
            patch.delenv(name)
    patch.setattr(dotenv, "load_dotenv", lambda *args, **kwargs: False)

    finder = _DatabaseImportBlocker(attempts)
    sys.meta_path.insert(0, finder)
    config._error_handling_isolation = patch, finder, attempts


def pytest_sessionfinish(session, exitstatus):
    import sys

    patch, finder, attempts = session.config._error_handling_isolation
    try:
        if attempts:
            reporter = session.config.pluginmanager.get_plugin("terminalreporter")
            if reporter is not None:
                reporter.write_line(f"차단된 실제 연결 시도: {len(attempts)}건")
            session.exitstatus = pytest.ExitCode.TESTS_FAILED
    finally:
        sys.meta_path.remove(finder)
        patch.undo()
