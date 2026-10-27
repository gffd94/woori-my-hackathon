"""환경 변수와 선택적 .env 파일에서 애플리케이션 설정을 로드한다."""

from __future__ import annotations

import ipaddress
import os
import re
from dataclasses import dataclass
from urllib.parse import urlsplit

from dotenv import load_dotenv


class ConfigurationError(ValueError):
    """설정값이 유효하지 않을 때 발생한다."""


def load_frontend_origins() -> tuple[str, ...]:
    """다른 서비스 설정과 독립적으로 CORS 허용 출처를 로드한다."""
    load_dotenv(override=False)
    value = os.getenv("FRONTEND_ORIGINS", "")
    if not value.strip():
        return ()

    origins: list[str] = []
    try:
        for item in value.split(","):
            origin = _normalize_frontend_origin(item)
            if origin not in origins:
                origins.append(origin)
    except ValueError:
        # URL 파서의 예외에도 입력이 포함될 수 있으므로 연쇄 표시하지 않는다.
        raise ConfigurationError(
            "FRONTEND_ORIGINS에 올바른 HTTP·HTTPS 출처 목록을 설정해 주세요."
        ) from None
    return tuple(origins)


def _normalize_frontend_origin(item: str) -> str:
    if any(ord(char) < 32 or ord(char) == 127 for char in item):
        raise ValueError
    origin = item.strip()
    if not origin or any(char.isspace() for char in origin):
        raise ValueError
    if any(char in origin for char in ("*", "@", "\\", "?", "#")):
        raise ValueError

    parsed = urlsplit(origin)
    host = parsed.hostname
    port = parsed.port
    if (
        parsed.scheme not in {"http", "https"}
        or not host
        or parsed.path
        or parsed.netloc.endswith(":")
        or port == 0
    ):
        raise ValueError

    if parsed.netloc.startswith("["):
        if not re.fullmatch(r"\[[0-9a-fA-F:.]+\](?::[0-9]+)?", parsed.netloc):
            raise ValueError
        host = f"[{ipaddress.IPv6Address(host).compressed}]"
    else:
        host = host.encode("idna").decode("ascii").lower()
        if re.fullmatch(r"[0-9]+(?:\.[0-9]+){3}", host):
            ipaddress.IPv4Address(host)
        if len(host) > 253 or any(
            not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label)
            for label in host.rstrip(".").split(".")
        ):
            raise ValueError
    if port is not None and port != {"http": 80, "https": 443}[parsed.scheme]:
        host = f"{host}:{port}"
    return f"{parsed.scheme}://{host}"


@dataclass(frozen=True)
class Settings:
    database_url: str | None
    admin_api_key: str | None
    llm_api_url: str | None
    llm_api_key: str | None
    llm_model: str | None
    llm_timeout_seconds: float
    embedding_api_url: str | None
    embedding_api_key: str | None
    embedding_model: str | None
    embedding_dimensions: int
    embedding_timeout_seconds: float
    report_fingerprint_key: str | None
    max_concurrent_requests: int
    test_database_url: str | None


def _optional_setting(name: str) -> str | None:
    value = os.getenv(name)
    if value is None or not value.strip():
        return None
    return value


def _positive_float(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None:
        return default

    try:
        number = float(value)
    except ValueError as exc:
        raise ConfigurationError(f"{name}은(는) 양수여야 합니다.") from exc

    if not (number > 0 and number < float("inf")):
        raise ConfigurationError(f"{name}은(는) 유한한 양수여야 합니다.")
    return number


def _positive_integer(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default

    try:
        number = int(value)
    except ValueError as exc:
        raise ConfigurationError(f"{name}은(는) 양의 정수여야 합니다.") from exc

    if number <= 0:
        raise ConfigurationError(f"{name}은(는) 양의 정수여야 합니다.")
    return number


def _embedding_dimensions() -> int:
    value = os.getenv("EMBEDDING_DIMENSIONS")
    if value is None:
        return 1536

    try:
        dimensions = int(value)
    except ValueError as exc:
        raise ConfigurationError(
            "EMBEDDING_DIMENSIONS는 1536이어야 합니다."
        ) from exc

    if dimensions != 1536:
        raise ConfigurationError("EMBEDDING_DIMENSIONS는 1536이어야 합니다.")
    return dimensions


def _validate_external_api_url(name: str, value: str | None) -> None:
    if value is None:
        return

    try:
        parsed = urlsplit(value)
        hostname = parsed.hostname
        parsed.port
    except ValueError as exc:
        raise ConfigurationError(f"{name}이(가) 올바른 URL이 아닙니다.") from exc

    if parsed.scheme.lower() != "https" or not hostname:
        raise ConfigurationError(f"{name}은(는) HTTPS URL이어야 합니다.")
    if parsed.username is not None or parsed.password is not None:
        raise ConfigurationError(f"{name}에 사용자 정보를 포함할 수 없습니다.")

    normalized_host = hostname.rstrip(".").lower()
    if normalized_host == "localhost" or normalized_host.endswith(".localhost"):
        raise ConfigurationError(f"{name}은(는) 로컬 주소를 대상으로 할 수 없습니다.")

    try:
        address = ipaddress.ip_address(normalized_host)
    except ValueError:
        return

    if (
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_unspecified
        or address.is_reserved
        or address.is_multicast
    ):
        raise ConfigurationError(f"{name}은(는) 로컬 또는 사설 IP를 대상으로 할 수 없습니다.")


def load_settings() -> Settings:
    """SPEC.md에 정의된 설정을 로드하고 검증한다."""
    load_dotenv(override=False)

    settings = Settings(
        database_url=_optional_setting("DATABASE_URL"),
        admin_api_key=_optional_setting("ADMIN_API_KEY"),
        llm_api_url=_optional_setting("LLM_API_URL"),
        llm_api_key=_optional_setting("LLM_API_KEY"),
        llm_model=_optional_setting("LLM_MODEL"),
        llm_timeout_seconds=_positive_float("LLM_TIMEOUT_SECONDS", 10.0),
        embedding_api_url=_optional_setting("EMBEDDING_API_URL"),
        embedding_api_key=_optional_setting("EMBEDDING_API_KEY"),
        embedding_model=_optional_setting("EMBEDDING_MODEL"),
        embedding_dimensions=_embedding_dimensions(),
        embedding_timeout_seconds=_positive_float(
            "EMBEDDING_TIMEOUT_SECONDS", 10.0
        ),
        report_fingerprint_key=_optional_setting("REPORT_FINGERPRINT_KEY"),
        max_concurrent_requests=_positive_integer("MAX_CONCURRENT_REQUESTS", 8),
        test_database_url=_optional_setting("TEST_DATABASE_URL"),
    )

    _validate_external_api_url("LLM_API_URL", settings.llm_api_url)
    _validate_external_api_url("EMBEDDING_API_URL", settings.embedding_api_url)
    return settings
