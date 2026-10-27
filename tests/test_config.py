import os
import subprocess
import sys
from pathlib import Path

import dotenv
import pytest

import app.config as config
from app.config import ConfigurationError, load_settings


SETTING_NAMES = (
    "DATABASE_URL",
    "ADMIN_API_KEY",
    "LLM_API_URL",
    "LLM_API_KEY",
    "LLM_MODEL",
    "LLM_TIMEOUT_SECONDS",
    "EMBEDDING_API_URL",
    "EMBEDDING_API_KEY",
    "EMBEDDING_MODEL",
    "EMBEDDING_DIMENSIONS",
    "EMBEDDING_TIMEOUT_SECONDS",
    "REPORT_FINGERPRINT_KEY",
    "MAX_CONCURRENT_REQUESTS",
    "TEST_DATABASE_URL",
)


@pytest.fixture(autouse=True)
def clear_settings_environment(monkeypatch):
    for name in SETTING_NAMES:
        monkeypatch.delenv(name, raising=False)
    # 경로 없는 load_dotenv는 cwd가 아니라 app/ 기준으로 저장소의 실제 .env를 찾는다.
    # 실제 값이 테스트 결과·실패 메시지에 섞이지 않도록 테스트 중에는 읽지 않는다.
    monkeypatch.setattr(config, "load_dotenv", lambda override=False: False)


def test_environment_variables_take_precedence_over_dotenv(tmp_path, monkeypatch):
    dotenv_file = tmp_path / ".env"
    dotenv_file.write_text(
        "LLM_MODEL=dotenv-model\nLLM_API_KEY=dotenv-key\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        config,
        "load_dotenv",
        lambda override: dotenv.load_dotenv(dotenv_path=dotenv_file, override=override),
    )
    monkeypatch.setenv("LLM_MODEL", "environment-model")

    settings = load_settings()

    assert settings.llm_model == "environment-model"
    assert settings.llm_api_key == "dotenv-key"


def test_missing_optional_settings_are_none_and_declared_defaults_are_used(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)

    settings = load_settings()

    assert settings.llm_timeout_seconds == 10.0
    assert settings.embedding_timeout_seconds == 10.0
    assert settings.embedding_dimensions == 1536
    assert settings.max_concurrent_requests == 8
    assert settings.database_url is None
    assert settings.admin_api_key is None
    assert settings.llm_api_url is None
    assert settings.llm_api_key is None
    assert settings.llm_model is None
    assert settings.embedding_api_url is None
    assert settings.embedding_api_key is None
    assert settings.embedding_model is None
    assert settings.report_fingerprint_key is None
    assert settings.test_database_url is None


@pytest.mark.parametrize(
    "name,value",
    [
        ("LLM_TIMEOUT_SECONDS", "invalid"),
        ("LLM_TIMEOUT_SECONDS", "0"),
        ("LLM_TIMEOUT_SECONDS", "-1"),
        ("LLM_TIMEOUT_SECONDS", "nan"),
        ("LLM_TIMEOUT_SECONDS", "inf"),
        ("EMBEDDING_TIMEOUT_SECONDS", "invalid"),
        ("EMBEDDING_TIMEOUT_SECONDS", "0"),
        ("EMBEDDING_TIMEOUT_SECONDS", "-1"),
        ("EMBEDDING_TIMEOUT_SECONDS", "nan"),
        ("EMBEDDING_TIMEOUT_SECONDS", "inf"),
    ],
)
def test_invalid_timeout_is_rejected(name, value, monkeypatch):
    monkeypatch.setenv(name, value)

    with pytest.raises(ConfigurationError):
        load_settings()


@pytest.mark.parametrize(
    "value",
    ["invalid", "0", "-1", "1.5"],
)
def test_invalid_max_concurrent_requests_is_rejected(value, monkeypatch):
    monkeypatch.setenv("MAX_CONCURRENT_REQUESTS", value)

    with pytest.raises(ConfigurationError):
        load_settings()


@pytest.mark.parametrize("value", ["invalid", "512", "1536.5", "0"])
def test_invalid_embedding_dimensions_are_rejected(value, monkeypatch):
    monkeypatch.setenv("EMBEDDING_DIMENSIONS", value)

    with pytest.raises(ConfigurationError):
        load_settings()


@pytest.mark.parametrize(
    "name,url",
    [
        ("LLM_API_URL", "http://api.example.test/v1"),
        ("LLM_API_URL", "https:///missing-host"),
        ("LLM_API_URL", "https://user:password@api.example.test/v1"),
        ("LLM_API_URL", "https://localhost/v1"),
        ("LLM_API_URL", "https://service.localhost/v1"),
        ("LLM_API_URL", "https://127.0.0.1/v1"),
        ("EMBEDDING_API_URL", "http://embedding.example.test/v1"),
        ("EMBEDDING_API_URL", "https://10.0.0.1/v1"),
        ("EMBEDDING_API_URL", "https://[::1]/v1"),
    ],
)
def test_disallowed_external_api_urls_are_rejected(name, url, monkeypatch):
    monkeypatch.setenv(name, url)

    with pytest.raises(ConfigurationError):
        load_settings()


def test_import_does_not_load_settings_or_initialize_database():
    project_root = Path(__file__).resolve().parents[1]
    script = """
import sys
from unittest.mock import patch
import dotenv

with patch("dotenv.load_dotenv", side_effect=AssertionError("dotenv loaded at import")):
    import app.config

assert not any(name == "sqlalchemy" or name.startswith("sqlalchemy.") for name in sys.modules)
assert not any(name == "psycopg" or name.startswith("psycopg.") for name in sys.modules)
"""

    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=project_root,
        check=False,
        capture_output=True,
        text=True,
        env=os.environ.copy(),
    )

    assert result.returncode == 0, result.stderr
