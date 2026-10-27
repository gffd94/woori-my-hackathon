"""실제 ASGI 경로로 POST /analyze 검증 (SPEC 3.3.2 A-11~A-17, 3.6 V, 3.7.2 N, R-04).

요청 source 관련 A-01~A-04는 feature/error-handling의 요청 스키마 테스트가 담당한다.
"""

import logging

import pytest
from fastapi.testclient import TestClient

import app.config as config
from app.main import app
from app.routers.analyze import get_analyzer
from tests.analyze_support import RISK_LLM, UNKNOWN_LLM, Fakes, block_real_calls, official  # noqa: F401

SAFE_MESSAGE = "가상은행 공지사항 안내 https://official.example/notice"
RESPONSE_FIELDS = {"status", "risk_level", "reasons", "matched_cases", "guide_type", "retrieval"}


@pytest.fixture
def client(block_real_calls):
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    assert block_real_calls == []


def _use(fakes):
    app.dependency_overrides[get_analyzer] = lambda: fakes.analyzer()
    return fakes


@pytest.mark.parametrize(
    "fakes, expected",
    [
        (Fakes(judgement=RISK_LLM), ("RISK", "high", "damage_stage")),
        (Fakes(lookup_result=official("official.example")), ("SAFE", "low", "prevention")),
        (Fakes(judgement=UNKNOWN_LLM), ("RISK", "low", "verification")),  # 공식 확인 안 된 URL만 있음
    ],
)
def test_A11_A13_A16_정상_판정은_200과_계약_필드(client, fakes, expected):
    _use(fakes)

    response = client.post("/analyze", json={"message": SAFE_MESSAGE})

    assert response.status_code == 200
    body = response.json()
    assert set(body) == RESPONSE_FIELDS
    assert (body["status"], body["risk_level"], body["guide_type"]) == expected
    assert body["matched_cases"] == 2
    assert body["retrieval"] == {
        "status": "completed", "method": "hybrid", "coverage": "complete", "reason_code": None
    }
    assert len(fakes.calls["save"]) == 1


def test_A15_검색_미완료면_matched_cases는_null(client):
    _use(Fakes(fail={"search"}))

    body = client.post("/analyze", json={"message": "택배 안내"}).json()

    assert body["matched_cases"] is None
    assert body["retrieval"]["status"] == "failed"


def test_A17_응답에_원문_score_내부_플래그가_없다(client):
    _use(Fakes(judgement=RISK_LLM))

    body = client.post("/analyze", json={"message": "비밀문구-ABC https://new.example"}).json()

    assert "비밀문구-ABC" not in str(body)
    assert not {"score", "source", "register_as_pending", "message"} & set(body)


@pytest.mark.parametrize("fakes_kwargs", [{"lookup_result": official("official.example")}, {"fail": {"judge"}}])
def test_V03_V04_V05_저장_실패는_503이고_내부_정보를_노출하지_않는다(client, caplog, fakes_kwargs):
    caplog.set_level(logging.DEBUG)
    fakes = _use(Fakes(**fakes_kwargs))
    fakes.fail.add("save")

    response = client.post("/analyze", json={"message": SAFE_MESSAGE + " 900101-1234567"})

    assert response.status_code == 503
    assert response.json() == {
        "detail": {
            "code": "VERDICT_LOG_UNAVAILABLE",
            "message": "판정 결과를 기록하지 못했습니다. 잠시 후 다시 시도해 주세요.",
        }
    }
    for leaked in ("SECRET-TEST-VALUE", "900101-1234567"):
        assert leaked not in response.text
        assert leaked not in caplog.text


def test_V07_잘못된_요청은_분석과_저장을_호출하지_않는다(client):
    fakes = _use(Fakes())

    response = client.post("/analyze", json={"message": "   "})

    assert response.status_code == 422
    assert all(calls == [] for calls in fakes.calls.values())


def test_R04_OpenAPI에_analyze가_있고_신고_관리자_API는_없다(client):
    paths = client.get("/openapi.json").json()["paths"]

    assert "post" in paths["/analyze"]
    assert not [path for path in paths if path.startswith(("/reports", "/admin"))]


def test_GET_루트_응답은_그대로다(client):
    assert client.get("/").json() == {"message": "Hackathon API is running!"}


# --- 실제 호출 차단 (N) ---

def test_N05_대역_없이_호출해도_실제_DB_외부_호출_없이_503(client, monkeypatch):
    # 실제 .env를 읽지 않게 한다 (N-04)
    monkeypatch.setattr(config, "load_dotenv", lambda **kwargs: False)

    response = client.post("/analyze", json={"message": SAFE_MESSAGE})

    # 실제 대조·저장이 아직 연결되지 않아 기록 저장 단계에서 503이 된다 (가짜 성공 없음)
    assert response.status_code == 503


def test_N01_앱_import와_시작만으로는_실제_호출이_없다(block_real_calls):
    with TestClient(app) as test_client:
        test_client.get("/docs")

    assert block_real_calls == []
