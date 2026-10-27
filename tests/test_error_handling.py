"""실제 앱의 오류 처리 구성을 격리된 HTTP 경계에서 검증한다."""

import logging

import pytest


@pytest.fixture
def client():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.main import app
    from app.schemas.analyze import AnalyzeRequest

    probe = FastAPI(middleware=list(app.user_middleware))
    probe.exception_handlers.update(app.exception_handlers)

    @probe.post("/__test__/request")
    async def accept_request(body: AnalyzeRequest):
        return {"accepted": True}

    @probe.post("/__test__/crash")
    async def crash(body: AnalyzeRequest):
        raise RuntimeError(f"TEST_INTERNAL_SECRET: {body.message}")

    @probe.get("/__test__/bad-response", response_model=AnalyzeRequest)
    async def bad_response():
        return {"message": None, "source": "TEST_RESPONSE_SECRET"}

    with TestClient(probe, raise_server_exceptions=False) as test_client:
        yield test_client


def test_요청_검증_실패는_원문과_상세를_숨긴_고정_422다(client, caplog):
    caplog.set_level(logging.DEBUG)

    response = client.post(
        "/__test__/request",
        json={"message": "TEST_REQUEST_SECRET", "source": "TEST_SOURCE_SECRET"},
    )

    assert response.status_code == 422
    assert response.json() == {
        "detail": {
            "code": "REQUEST_VALIDATION_ERROR",
            "message": "요청 입력을 확인해 주세요.",
        }
    }
    for secret in ("TEST_REQUEST_SECRET", "TEST_SOURCE_SECRET"):
        assert secret not in response.text
        assert secret not in caplog.text


def test_내부_예외는_요청과_예외를_숨긴_고정_500이다(client, caplog):
    caplog.set_level(logging.DEBUG)

    response = client.post("/__test__/crash", json={"message": "TEST_REQUEST_SECRET"})

    assert response.status_code == 500
    assert response.json() == {
        "detail": {
            "code": "INTERNAL_SERVER_ERROR",
            "message": "서버 오류가 발생했습니다.",
        }
    }
    for secret in ("TEST_REQUEST_SECRET", "TEST_INTERNAL_SECRET", "RuntimeError"):
        assert secret not in response.text
        assert secret not in caplog.text


def test_처리된_500은_ASGI_호출자에게_민감한_예외를_재전파하지_않는다(client, caplog):
    from fastapi.testclient import TestClient

    caplog.set_level(logging.DEBUG)

    with TestClient(client.app, raise_server_exceptions=True) as strict_client:
        response = strict_client.post(
            "/__test__/crash", json={"message": "TEST_REQUEST_SECRET"}
        )

    assert response.status_code == 500
    assert response.json() == {
        "detail": {
            "code": "INTERNAL_SERVER_ERROR",
            "message": "서버 오류가 발생했습니다.",
        }
    }
    assert "TEST_REQUEST_SECRET" not in caplog.text
    assert "TEST_INTERNAL_SECRET" not in caplog.text


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"message": ""},
        {"message": " \t\n"},
        {"message": "가" * 5001},
        {"message": None},
        {"message": 123},
        {"message": []},
        {"message": "TEST_REQUEST_SECRET", "source": None},
        {"message": "TEST_REQUEST_SECRET", "TEST_FIELD_SECRET": "TEST_VALUE_SECRET"},
    ],
)
def test_잘못된_요청은_상세와_입력값_없이_422다(client, caplog, body):
    caplog.set_level(logging.DEBUG)

    response = client.post(
        "/__test__/request",
        json=body,
        headers={"Authorization": "Bearer TEST_HEADER_SECRET"},
    )

    assert response.status_code == 422
    assert response.json() == {
        "detail": {
            "code": "REQUEST_VALIDATION_ERROR",
            "message": "요청 입력을 확인해 주세요.",
        }
    }
    for secret in ("TEST_REQUEST_SECRET", "TEST_FIELD_SECRET", "TEST_VALUE_SECRET", "TEST_HEADER_SECRET"):
        assert secret not in response.text
        assert secret not in caplog.text


def test_잘못된_JSON도_본문을_노출하지_않는_422다(client, caplog):
    caplog.set_level(logging.DEBUG)

    response = client.post(
        "/__test__/request",
        content='{"message": "TEST_JSON_SECRET",',
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 422
    assert response.json() == {
        "detail": {
            "code": "REQUEST_VALIDATION_ERROR",
            "message": "요청 입력을 확인해 주세요.",
        }
    }
    assert "TEST_JSON_SECRET" not in response.text
    assert "TEST_JSON_SECRET" not in caplog.text


def test_서버_응답_검증_오류를_요청_422로_바꾸지_않는다(client, caplog):
    caplog.set_level(logging.DEBUG)

    response = client.get("/__test__/bad-response")

    assert response.status_code == 500
    assert response.json() == {
        "detail": {
            "code": "INTERNAL_SERVER_ERROR",
            "message": "서버 오류가 발생했습니다.",
        }
    }
    assert "TEST_RESPONSE_SECRET" not in response.text
    assert "TEST_RESPONSE_SECRET" not in caplog.text


@pytest.mark.parametrize("source", [None, "share", "paste"])
def test_유효한_요청은_오류_처리로_바뀌지_않는다(client, caplog, source):
    caplog.set_level(logging.DEBUG)
    body = {"message": "TEST_SUCCESS_SECRET"}
    if source is not None:
        body["source"] = source

    response = client.post("/__test__/request", json=body)

    assert response.status_code == 200
    assert response.json() == {"accepted": True}
    assert "TEST_SUCCESS_SECRET" not in caplog.text
