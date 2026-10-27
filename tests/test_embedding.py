"""임베딩 호출 경계와 응답 검증 (SPEC 2.8, S-08·S-09). 실제 API는 호출하지 않는다."""

import math

import pytest

from app.config import Settings
from app.services.embedding import EmbeddingError, request_embedding, validate_embedding

VECTOR = [0.01] * 1536


def _settings(**overrides):
    data = dict(
        database_url=None,
        admin_api_key=None,
        llm_api_url=None,
        llm_api_key=None,
        llm_model=None,
        llm_timeout_seconds=10.0,
        embedding_api_url="https://embedding.example/v1/embeddings",
        embedding_api_key="test-embedding-key",
        embedding_model="test-embedding-model",
        embedding_dimensions=1536,
        embedding_timeout_seconds=10.0,
        report_fingerprint_key=None,
        max_concurrent_requests=8,
        test_database_url=None,
    )
    data.update(overrides)
    return Settings(**data)


def _response(vector=VECTOR, model="test-embedding-model"):
    return {"model": model, "data": [{"embedding": vector}]}


def test_정상_응답이면_1536차원_벡터를_돌려준다():
    calls = []

    def fake_post(url, headers, body, timeout):
        calls.append((url, headers, body, timeout))
        return _response()

    vector = request_embedding("마스킹된 문자", settings=_settings(), http_post=fake_post)

    assert vector == VECTOR
    url, headers, body, timeout = calls[0]
    assert url == "https://embedding.example/v1/embeddings"
    assert headers["Authorization"] == "Bearer test-embedding-key"
    assert body == {"model": "test-embedding-model", "input": "마스킹된 문자"}
    assert timeout == 10.0


@pytest.mark.parametrize(
    "vector",
    [
        [0.1] * 1535,
        [0.1] * 1537,
        [0.0] * 1536,
        [math.nan] + [0.1] * 1535,
        [math.inf] + [0.1] * 1535,
        ["0.1"] * 1536,
        [True] * 1536,
        None,
    ],
)
def test_차원_영벡터_NaN_무한대_타입이_틀리면_거부한다(vector):
    with pytest.raises(EmbeddingError):
        validate_embedding(vector)


@pytest.mark.parametrize(
    "response",
    [
        {},
        {"data": []},
        {"data": [{}]},
        _response(model="other-model"),
        _response(vector=[0.1] * 3),
    ],
)
def test_응답_형식이나_모델이_다르면_EmbeddingError(response):
    with pytest.raises(EmbeddingError):
        request_embedding("문자", settings=_settings(), http_post=lambda *a: response)


@pytest.mark.parametrize("missing", ["embedding_api_url", "embedding_api_key", "embedding_model"])
def test_설정이_없으면_호출하지_않고_거부한다(missing):
    def must_not_call(*args):
        pytest.fail("설정이 없으면 외부 호출을 하면 안 됩니다")

    with pytest.raises(EmbeddingError):
        request_embedding("문자", settings=_settings(**{missing: None}), http_post=must_not_call)


def test_호출_오류는_재시도하지_않고_키를_노출하지_않는다():
    calls = []

    def failing_post(*args):
        calls.append(args)
        raise TimeoutError("timeout with test-embedding-key")

    with pytest.raises(EmbeddingError) as excinfo:
        request_embedding("문자", settings=_settings(), http_post=failing_post)

    assert len(calls) == 1
    assert "test-embedding-key" not in str(excinfo.value)
    assert excinfo.value.__cause__ is None
