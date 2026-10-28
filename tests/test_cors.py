"""실제 dotenv·DB·네트워크 없이 CORS 설정과 HTTP 계약을 검증한다."""

from pathlib import Path
import logging
import runpy
import traceback

import pytest

import app.config as config


ORIGIN = "http://localhost:5173"


@pytest.fixture(autouse=True)
def isolate_frontend_origins(monkeypatch):
    monkeypatch.delenv("FRONTEND_ORIGINS", raising=False)


def test_missing_origins_allow_no_cross_origin_access():
    assert config.load_frontend_origins() == ()


@pytest.mark.parametrize(
    "value,expected",
    [
        ("", ()),
        ("   ", ()),
        ("http://localhost:5173", ("http://localhost:5173",)),
        (
            " HTTP://LOCALHOST:5173 , https://ui.example.test:443, http://localhost:5173 ",
            ("http://localhost:5173", "https://ui.example.test"),
        ),
        ("http://ui.example.test:80", ("http://ui.example.test",)),
        ("https://ui.example.test:8443", ("https://ui.example.test:8443",)),
        ("http://[::1]:5173", ("http://[::1]:5173",)),
    ],
)
def test_origins_are_trimmed_normalized_and_deduplicated(monkeypatch, value, expected):
    monkeypatch.setenv("FRONTEND_ORIGINS", value)
    assert config.load_frontend_origins() == expected


@pytest.mark.parametrize(
    "origin,expected",
    [
        ("http://127.0.0.1", "http://127.0.0.1"),
        ("http://192.168.1.10", "http://192.168.1.10"),
        ("http://0.0.0.0", "http://0.0.0.0"),
        ("http://255.255.255.255", "http://255.255.255.255"),
        ("https://192.168.1.10:443", "https://192.168.1.10"),
        ("http://127.0.0.1:5173", "http://127.0.0.1:5173"),
    ],
)
def test_valid_ipv4_origins_keep_existing_normalization(monkeypatch, origin, expected):
    monkeypatch.setenv("FRONTEND_ORIGINS", origin)
    assert config.load_frontend_origins() == (expected,)


@pytest.mark.parametrize(
    "host",
    ["999.999.999.999", "256.1.1.1", "1.256.1.1", "1.1.256.1", "1.1.1.256"],
)
def test_ipv4_octets_outside_range_are_rejected_without_exposing_input(monkeypatch, host):
    origin = f"http://{host}"
    monkeypatch.setenv("FRONTEND_ORIGINS", origin)

    with pytest.raises(config.ConfigurationError) as caught:
        config.load_frontend_origins()

    assert str(caught.value) == "FRONTEND_ORIGINS에 올바른 HTTP·HTTPS 출처 목록을 설정해 주세요."
    assert host not in "".join(traceback.format_exception(caught.value))


@pytest.mark.parametrize(
    "value",
    [
        "*", "null", "https://*.example.test", "ftp://ui.example.test",
        "ui.example.test", "https:///missing-host", "https://",
        "https://TEST_USER:TEST_PASSWORD@ui.example.test",
        "https://ui.example.test/", "https://ui.example.test/path",
        "https://ui.example.test?", "https://ui.example.test?q=TEST_QUERY",
        "https://ui.example.test#", "https://ui.example.test#TEST_FRAGMENT",
        "https://ui.example.test:", "https://ui.example.test:0",
        "https://ui.example.test:65536", "https://ui.example.test:TEST_PORT",
        "https://ui.example.test:-1", "http://[TEST_INVALID_IPV6]:5173",
        "http://[::1]suffix", "http://[::1%eth0]:5173", "http://[v1.example]:5173",
        "https://ui.exam ple.test", "https://ui.example.test\\path",
        "https://ui.exam\nple.test", "https://ui.exam\tple.test",
        "https://ui.example.test\x7f", "https://bad_host.example.test",
        "https://.example.test", "https://-bad.example.test",
        "http://localhost:5173,", ",http://localhost:5173", ",",
        "http://localhost:5173,,https://ui.example.test",
        "http://localhost:5173,https://TEST_SECRET@ui.example.test",
    ],
    ids=lambda value: f"invalid-{len(value)}",
)
def test_invalid_origins_fail_without_exposing_configuration(monkeypatch, value):
    monkeypatch.setenv("FRONTEND_ORIGINS", value)

    with pytest.raises(config.ConfigurationError) as caught:
        config.load_frontend_origins()

    assert str(caught.value) == "FRONTEND_ORIGINS에 올바른 HTTP·HTTPS 출처 목록을 설정해 주세요."
    rendered = "".join(traceback.format_exception(caught.value))
    for secret in ("TEST_USER", "TEST_PASSWORD", "TEST_QUERY", "TEST_FRAGMENT", "TEST_PORT", "TEST_SECRET"):
        assert secret not in rendered


def test_cors_loader_ignores_unrelated_invalid_service_settings(monkeypatch):
    monkeypatch.setenv("FRONTEND_ORIGINS", "http://localhost:5173")
    monkeypatch.setenv("EMBEDDING_DIMENSIONS", "TEST_INVALID_DIMENSIONS")
    assert config.load_frontend_origins() == ("http://localhost:5173",)


def load_isolated_app():
    # 모듈 캐시를 바꾸거나 운영 앱에 테스트 경로를 추가하지 않는다.
    return runpy.run_path(str(Path(__file__).resolve().parents[1] / "app/main.py"))["app"]


@pytest.fixture
def cors_app(monkeypatch):
    monkeypatch.setenv("FRONTEND_ORIGINS", f"{ORIGIN},https://ui.example.test")
    return load_isolated_app()


@pytest.fixture
def client(cors_app):
    from fastapi.testclient import TestClient

    with TestClient(cors_app) as test_client:
        yield test_client


@pytest.fixture
def analyze_callbacks(cors_app, monkeypatch):
    from app.routers.analyze import get_analyzer
    from app.services.analyzer import Analyzer, LookupResult, SearchOutcome
    from app.services.llm_judge import LLMJudgement

    state = {"fail_save": False, "calls": [], "save_attempts": [], "saved": []}

    def lookup(extracted):
        state["calls"].append("lookup")
        return LookupResult()

    def embed(masked):
        state["calls"].append("embed")
        return [0.01] * 1536

    def search(masked, vector):
        state["calls"].append("search")
        return SearchOutcome(status="completed", method="hybrid", coverage="complete")

    def judge(masked, cards, labels):
        state["calls"].append("judge")
        return LLMJudgement(suspicious=False, signals=[], reasons=[], suggestion="SAFE")

    def save(record):
        state["calls"].append("save")
        state["save_attempts"].append(record)
        if state["fail_save"]:
            raise RuntimeError("TEST_ANALYZE_SAVE_SECRET")
        state["saved"].append(record)

    analyzer = Analyzer(lookup=lookup, embed=embed, search=search, judge=judge, save=save)
    previous_overrides = dict(cors_app.dependency_overrides)
    with monkeypatch.context() as override:
        override.setitem(cors_app.dependency_overrides, get_analyzer, lambda: analyzer)
        yield state
    assert cors_app.dependency_overrides == previous_overrides


def assert_cors_headers(response, origin=ORIGIN):
    assert response.headers["access-control-allow-origin"] == origin
    assert "origin" in {part.strip().lower() for part in response.headers["vary"].split(",")}
    assert "access-control-allow-credentials" not in response.headers
    assert "access-control-expose-headers" not in response.headers


@pytest.mark.parametrize("origin", [ORIGIN, "https://ui.example.test"])
def test_allowed_origins_receive_explicit_cors_headers(client, origin):
    response = client.get("/", headers={"Origin": origin})
    assert response.status_code == 200
    assert response.json() == {"message": "Hackathon API is running!"}
    assert_cors_headers(response, origin)


@pytest.mark.parametrize("origin", [None, "https://blocked.example.test", "null"])
def test_other_origins_keep_normal_response_without_allow_origin(client, origin):
    headers = {} if origin is None else {"Origin": origin}
    response = client.get("/", headers=headers)
    assert response.status_code == 200
    assert response.json() == {"message": "Hackathon API is running!"}
    assert "access-control-allow-origin" not in response.headers
    assert "access-control-allow-credentials" not in response.headers


def test_missing_configuration_does_not_allow_development_origin():
    from fastapi.testclient import TestClient

    with TestClient(load_isolated_app()) as test_client:
        response = test_client.get("/", headers={"Origin": ORIGIN})
    assert response.status_code == 200
    assert "access-control-allow-origin" not in response.headers


def test_invalid_configuration_fails_during_app_construction(monkeypatch):
    monkeypatch.setenv("FRONTEND_ORIGINS", "https://TEST_STARTUP_SECRET@ui.example.test")
    with pytest.raises(config.ConfigurationError) as caught:
        load_isolated_app()
    assert "TEST_STARTUP_SECRET" not in "".join(traceback.format_exception(caught.value))


def test_environment_is_not_read_again_per_request(client, monkeypatch):
    monkeypatch.setenv("FRONTEND_ORIGINS", "TEST_INVALID_AFTER_STARTUP")
    response = client.get("/", headers={"Origin": ORIGIN})
    assert response.status_code == 200
    assert_cors_headers(response)


def test_origin_configuration_is_restored_between_test_contexts(monkeypatch):
    with monkeypatch.context() as temporary:
        temporary.setenv("FRONTEND_ORIGINS", ORIGIN)
        assert config.load_frontend_origins() == (ORIGIN,)
    assert config.load_frontend_origins() == ()


def test_allowed_preflight_advertises_post_and_content_type(client):
    response = client.options(
        "/analyze",
        headers={
            "Origin": ORIGIN,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert response.status_code == 200
    assert_cors_headers(response)
    assert response.headers["access-control-allow-methods"] == "POST"
    assert response.headers["access-control-max-age"] == "600"
    assert {part.strip().lower() for part in response.headers["access-control-allow-headers"].split(",")} == {
        "accept", "accept-language", "content-language", "content-type",
    }


@pytest.mark.parametrize(
    "origin,method,requested_headers",
    [
        ("https://blocked.example.test", "POST", "content-type"),
        (ORIGIN, "DELETE", "content-type"),
        (ORIGIN, "POST", "authorization"),
    ],
)
def test_disallowed_preflight_is_rejected(client, origin, method, requested_headers):
    response = client.options(
        "/analyze",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": method,
            "Access-Control-Request-Headers": requested_headers,
        },
    )
    assert response.status_code == 400
    if origin == ORIGIN:
        # 허용 출처여도 메서드·헤더 검증은 별도로 실패할 수 있다.
        assert_cors_headers(response)
    else:
        assert "access-control-allow-origin" not in response.headers


@pytest.fixture
def error_client(cors_app):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.schemas.analyze import AnalyzeRequest

    probe = FastAPI(middleware=list(cors_app.user_middleware))
    probe.exception_handlers.update(cors_app.exception_handlers)

    @probe.post("/__test__/request")
    async def accept(body: AnalyzeRequest):
        return {"accepted": True}

    @probe.post("/__test__/crash")
    async def crash(body: AnalyzeRequest):
        raise RuntimeError(f"TEST_EXCEPTION_SECRET: {body.message}")

    @probe.get("/__test__/bad-response", response_model=AnalyzeRequest)
    async def bad_response():
        return {"message": None, "source": "TEST_RESPONSE_SECRET"}

    with TestClient(probe, raise_server_exceptions=True) as test_client:
        yield test_client


@pytest.mark.parametrize("case", ["source", "extra", "json", "crash", "response"])
def test_error_responses_keep_fixed_body_cors_and_no_secrets(error_client, caplog, case):
    caplog.set_level(logging.DEBUG)
    headers = {"Origin": ORIGIN, "Authorization": "Bearer TEST_HEADER_SECRET"}
    if case == "response":
        response = error_client.get("/__test__/bad-response", headers=headers)
    elif case == "json":
        response = error_client.post(
            "/__test__/request", content='{"message": "TEST_BODY_SECRET",',
            headers={**headers, "Content-Type": "application/json"},
        )
    else:
        body = {"message": "TEST_BODY_SECRET"}
        if case == "source":
            body["source"] = "TEST_SOURCE_SECRET"
        elif case == "extra":
            body["TEST_FIELD_SECRET"] = "TEST_EXTRA_SECRET"
        path = "/__test__/crash" if case == "crash" else "/__test__/request"
        response = error_client.post(path, json=body, headers=headers)

    server_error = case in {"crash", "response"}
    assert response.status_code == (500 if server_error else 422)
    assert response.json() == {
        "detail": {
            "code": "INTERNAL_SERVER_ERROR" if server_error else "REQUEST_VALIDATION_ERROR",
            "message": "서버 오류가 발생했습니다." if server_error else "요청 입력을 확인해 주세요.",
        }
    }
    assert_cors_headers(response)
    for secret in (
        "TEST_BODY_SECRET", "TEST_HEADER_SECRET", "TEST_SOURCE_SECRET",
        "TEST_FIELD_SECRET", "TEST_EXTRA_SECRET", "TEST_EXCEPTION_SECRET",
        "TEST_RESPONSE_SECRET", "RuntimeError", "ResponseValidationError",
    ):
        assert secret not in response.text
        assert secret not in caplog.text


@pytest.mark.parametrize(
    "method,path,status,body",
    [
        ("get", "/", 200, {"message": "Hackathon API is running!"}),
        ("get", "/missing", 404, {"detail": "Not Found"}),
        ("post", "/", 405, {"detail": "Method Not Allowed"}),
    ],
)
def test_existing_http_contracts_are_preserved(client, method, path, status, body):
    response = getattr(client, method)(path, headers={"Origin": ORIGIN})
    assert response.status_code == status
    assert response.json() == body
    assert_cors_headers(response)
    if status == 405:
        assert response.headers["allow"] == "GET"


def test_docs_openapi_and_production_route_set_are_preserved(client):
    docs = client.get("/docs", headers={"Origin": ORIGIN})
    schema = client.get("/openapi.json", headers={"Origin": ORIGIN})
    assert docs.status_code == 200
    assert "/openapi.json" in docs.text
    assert schema.status_code == 200
    paths = schema.json()["paths"]
    assert set(paths) == {"/", "/analyze"}
    assert "post" in paths["/analyze"]
    assert_cors_headers(docs)
    assert_cors_headers(schema)
    analyze = client.get("/analyze", headers={"Origin": ORIGIN})
    assert analyze.status_code == 405
    assert analyze.headers["allow"] == "POST"
    assert_cors_headers(analyze)
    for path in ("/reports", "/admin/cases", "/__test__/request"):
        assert client.post(path, json={"message": "가상 안내"}).status_code == 404


def test_analyze_post_success_has_cors(analyze_callbacks, client, caplog):
    caplog.set_level(logging.DEBUG)
    response = client.post(
        "/analyze",
        json={"message": "가상 공지 TEST_ANALYZE_BODY_SECRET"},
        headers={"Origin": ORIGIN},
    )

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"status", "risk_level", "reasons", "matched_cases", "guide_type", "retrieval", "evidence"}
    assert (body["status"], body["risk_level"], body["guide_type"]) == ("SAFE", "low", "prevention")
    assert isinstance(body["reasons"], list)
    assert all(isinstance(reason, str) for reason in body["reasons"])
    assert body["matched_cases"] == 0
    assert body["retrieval"] == {
        "status": "completed", "method": "hybrid", "coverage": "complete", "reason_code": None,
    }
    assert len(analyze_callbacks["saved"]) == 1
    assert set(analyze_callbacks["calls"]) == {"lookup", "embed", "search", "judge", "save"}
    assert_cors_headers(response)
    assert "TEST_ANALYZE_BODY_SECRET" not in response.text
    assert "TEST_ANALYZE_BODY_SECRET" not in caplog.text


def test_analyze_post_save_failure_has_cors(analyze_callbacks, client, caplog):
    caplog.set_level(logging.DEBUG)
    analyze_callbacks["fail_save"] = True
    response = client.post(
        "/analyze",
        json={"message": "가상 공지 TEST_ANALYZE_BODY_SECRET"},
        headers={"Origin": ORIGIN},
    )

    assert response.status_code == 503
    assert response.json() == {
        "detail": {
            "code": "VERDICT_LOG_UNAVAILABLE",
            "message": "판정 결과를 기록하지 못했습니다. 잠시 후 다시 시도해 주세요.",
        }
    }
    assert len(analyze_callbacks["save_attempts"]) == 1
    assert analyze_callbacks["saved"] == []
    assert set(analyze_callbacks["calls"]) == {"lookup", "embed", "search", "judge", "save"}
    assert_cors_headers(response)
    for secret in ("TEST_ANALYZE_BODY_SECRET", "TEST_ANALYZE_SAVE_SECRET"):
        assert secret not in response.text
        assert secret not in caplog.text
    assert "RuntimeError" not in response.text
    assert "VerdictLogError" not in response.text
