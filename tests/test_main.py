"""실제 앱의 기존 경로와 비대상 기능 보존을 검증한다."""

import logging

import pytest


@pytest.fixture
def client():
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client


def test_GET_루트의_기존_상태와_응답을_보존한다(client, caplog):
    caplog.set_level(logging.DEBUG)

    response = client.get("/", headers={"Authorization": "Bearer TEST_HEADER_SECRET"})

    assert response.status_code == 200
    assert response.json() == {"message": "Hackathon API is running!"}
    assert "TEST_HEADER_SECRET" not in response.text
    assert "TEST_HEADER_SECRET" not in caplog.text


def test_docs와_OpenAPI는_DB와_외부_설정_없이_제공된다(client):
    docs = client.get("/docs")
    schema = client.get("/openapi.json")

    assert docs.status_code == 200
    assert "/openapi.json" in docs.text
    assert schema.status_code == 200
    assert set(schema.json()["paths"]) == {"/"}


def test_등록되지_않은_경로의_기존_404를_보존한다(client):
    response = client.get("/__test__/missing")

    assert response.status_code == 404
    assert response.json() == {"detail": "Not Found"}


def test_허용하지_않은_메서드의_기존_405와_Allow를_보존한다(client):
    response = client.post("/")

    assert response.status_code == 405
    assert response.json() == {"detail": "Method Not Allowed"}
    assert response.headers["allow"] == "GET"


def test_분석과_신고와_관리자_라우트를_이번에_추가하지_않는다(client):
    for path in ("/analyze", "/reports", "/admin/cases", "/__test__/request"):
        assert client.post(path, json={"message": "가상 안내"}).status_code == 404
