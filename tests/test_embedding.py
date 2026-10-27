"""외부 임베딩 응답 검증(SPEC 2.8, 3.5.3). 실제 API는 호출하지 않고 post 대역을 쓴다."""

import urllib.error

import pytest

from app.config import Settings
from app.services.embedding import (
    EmbeddingError,
    embed_texts,
    pattern_embedding_text,
)


def make_settings(**overrides):
    values = dict(
        database_url=None, admin_api_key=None,
        llm_api_url=None, llm_api_key=None, llm_model=None, llm_timeout_seconds=10.0,
        embedding_api_url="https://embedding.example/v1/embeddings",
        embedding_api_key="test-key",
        embedding_model="text-embedding-3-small",
        embedding_dimensions=1536, embedding_timeout_seconds=10.0,
        report_fingerprint_key=None, max_concurrent_requests=8, test_database_url=None,
    )
    values.update(overrides)
    return Settings(**values)


def vector(first=0.1):
    return [first] + [0.01] * 1535


class FakePost:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.calls = []

    def __call__(self, url, headers, body, timeout):
        self.calls.append((url, headers, body, timeout))
        if self.error:
            raise self.error
        return self.response


def test_정상_응답은_입력_순서대로_벡터를_돌려준다():
    post = FakePost({
        "model": "text-embedding-3-small",
        "data": [
            {"index": 1, "embedding": vector(0.2)},
            {"index": 0, "embedding": vector(0.1)},
        ],
    })
    result = embed_texts(["가상 문구 하나", "가상 문구 둘"], settings=make_settings(), post=post)

    assert [v[0] for v in result] == [0.1, 0.2]
    url, headers, body, timeout = post.calls[0]
    assert url == "https://embedding.example/v1/embeddings"
    assert headers["Authorization"] == "Bearer test-key"
    assert body == {"model": "text-embedding-3-small", "input": ["가상 문구 하나", "가상 문구 둘"]}
    assert timeout == 10.0


@pytest.mark.parametrize("bad", [
    [0.1] * 1535,
    [0.1] * 1537,
    [float("nan")] + [0.1] * 1535,
    [float("inf")] + [0.1] * 1535,
    [0.0] * 1536,
    ["0.1"] * 1536,
])
def test_차원이나_수치가_잘못된_응답은_생성_실패다(bad):
    post = FakePost({"model": "text-embedding-3-small", "data": [{"index": 0, "embedding": bad}]})
    with pytest.raises(EmbeddingError):
        embed_texts(["가상 문구"], settings=make_settings(), post=post)


@pytest.mark.parametrize("response", [
    None,
    {},
    {"data": []},
    {"data": [{"index": 0}]},
    {"data": [{"index": 5, "embedding": [0.1] * 1536}]},
    {"model": "other-model", "data": [{"index": 0, "embedding": [0.1] * 1536}]},
])
def test_응답_구조나_모델이_다르면_생성_실패다(response):
    post = FakePost(response)
    with pytest.raises(EmbeddingError):
        embed_texts(["가상 문구"], settings=make_settings(), post=post)


@pytest.mark.parametrize("error", [
    urllib.error.URLError("연결 실패"),
    TimeoutError("시간 초과"),
    ValueError("JSON 아님"),
])
def test_연결_오류와_timeout은_생성_실패이고_키를_노출하지_않는다(error):
    post = FakePost(error=error)
    with pytest.raises(EmbeddingError) as exc_info:
        embed_texts(["가상 문구"], settings=make_settings(), post=post)
    assert "test-key" not in str(exc_info.value)


@pytest.mark.parametrize("missing", ["embedding_api_url", "embedding_api_key", "embedding_model"])
def test_설정이_없으면_호출하지_않고_실패한다(missing):
    post = FakePost({"data": []})
    with pytest.raises(EmbeddingError):
        embed_texts(["가상 문구"], settings=make_settings(**{missing: None}), post=post)
    assert post.calls == []


def test_빈_입력은_호출하지_않는다():
    post = FakePost({"data": []})
    assert embed_texts([], settings=make_settings(), post=post) == []
    assert post.calls == []


def test_수법_카드_임베딩_문구는_고정된_순서로_만든다():
    text = pattern_embedding_text({
        "name": "가상 택배 주소 정정",
        "summary": "주소 확인을 핑계로 링크 접속을 유도한다.",
        "impersonation": "택배사",
        "lure_action": "링크 접속",
        "triggers": ["주소 불명", "링크"],
        "example_messages": [
            {"text": "[가상택배] 주소 불명으로 보관 중", "type": "sms", "source_post_id": "1"},
            {"text": "  ", "type": "sms", "source_post_id": "2"},
        ],
    })

    assert text == (
        "수법: 가상 택배 주소 정정\n"
        "설명: 주소 확인을 핑계로 링크 접속을 유도한다.\n"
        "사칭 대상: 택배사\n"
        "유도 행동: 링크 접속\n"
        "위험 신호: 주소 불명, 링크\n"
        "예시 문자:\n"
        "- [가상택배] 주소 불명으로 보관 중"
    )


def test_비어있는_항목은_수법_카드_문구에서_뺀다():
    text = pattern_embedding_text({"name": "가상 수법", "summary": None, "triggers": [], "example_messages": []})
    assert text == "수법: 가상 수법"
