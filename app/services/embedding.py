"""질의 임베딩 호출과 응답 검증 (SPEC 2.8).

자동 재시도·절단·패딩을 하지 않는다. 오류 메시지에 키·응답 전문을 넣지 않는다.
요청 형식은 OpenAI 호환 임베딩 API({"model", "input"} → data[0].embedding)를 따른다.
"""

import json
import math
import urllib.request
from typing import Any, Callable

from app.config import Settings

EMBEDDING_DIMENSIONS = 1536

# (url, headers, body, timeout) -> 응답 JSON
HttpPost = Callable[[str, dict[str, str], dict[str, Any], float], dict[str, Any]]


class EmbeddingError(Exception):
    """임베딩 생성·검증 실패. 호출자는 검색 failed로 처리한다."""


def validate_embedding(vector: Any) -> list[float]:
    """1536차원·유한한 숫자·영벡터 아님을 확인한다. bool·문자열 숫자는 거부한다."""
    if not isinstance(vector, (list, tuple)) or len(vector) != EMBEDDING_DIMENSIONS:
        raise EmbeddingError(f"임베딩은 {EMBEDDING_DIMENSIONS}차원이어야 합니다")
    try:
        finite = all(type(value) in (int, float) and math.isfinite(value) for value in vector)
    except OverflowError:
        finite = False
    if not finite:
        raise EmbeddingError("임베딩은 유한한 숫자여야 합니다")
    if not any(vector):
        raise EmbeddingError("영벡터 임베딩은 사용할 수 없습니다")
    return [float(value) for value in vector]


def _post_json(url: str, headers: dict[str, str], body: dict[str, Any], timeout: float) -> dict[str, Any]:
    request = urllib.request.Request(url, data=json.dumps(body).encode(), headers=headers, method="POST")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.load(response)


def request_embedding(text: str, *, settings: Settings, http_post: HttpPost | None = None) -> list[float]:
    if not (settings.embedding_api_url and settings.embedding_api_key and settings.embedding_model):
        raise EmbeddingError("임베딩 설정이 없습니다")

    post = http_post or _post_json
    try:
        data = post(
            settings.embedding_api_url,
            {"Authorization": f"Bearer {settings.embedding_api_key}", "Content-Type": "application/json"},
            {"model": settings.embedding_model, "input": text},
            settings.embedding_timeout_seconds,
        )
    except Exception:
        # 원래 예외 문구에 키·URL이 섞일 수 있어 연결하지 않는다
        raise EmbeddingError("임베딩 API 호출에 실패했습니다") from None

    try:
        vector = data["data"][0]["embedding"]
        model = data.get("model")
    except (KeyError, IndexError, TypeError, AttributeError):
        raise EmbeddingError("임베딩 응답 형식이 올바르지 않습니다") from None
    # 같은 차원이어도 다른 모델의 벡터는 비교할 수 없다 (SPEC 2.8)
    if model is not None and model != settings.embedding_model:
        raise EmbeddingError("임베딩 응답 모델이 설정과 다릅니다")
    return validate_embedding(vector)
