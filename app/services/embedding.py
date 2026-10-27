"""외부 임베딩 HTTP 호출과 응답 검증(SPEC 2.8).

공급자 SDK 없이 OpenAI 호환 `/v1/embeddings` 형식으로 호출한다.
응답이 1,536차원이 아니거나 NaN·무한대·영벡터면 EmbeddingError로 실패시킨다.
절단·패딩·자동 차원 변환은 하지 않는다. 입력 문구의 개인정보 마스킹은 호출자가 한다.
"""

from __future__ import annotations

import json
import math
import urllib.request
from collections.abc import Mapping
from typing import Any, Callable

from app.config import Settings, load_settings

EMBEDDING_DIMENSIONS = 1536
# 수법 카드 문구 구성 방식. 바꾸면 전체 활성 수법 카드를 재색인해야 한다.
PATTERN_TEXT_VERSION = "pattern-text-v1"

EmbeddingPost = Callable[[str, dict[str, str], dict[str, Any], float], Any]


class EmbeddingError(RuntimeError):
    """임베딩 생성 실패. 메시지에 API 키나 입력 문구를 넣지 않는다."""


def _post_json(url: str, headers: dict[str, str], body: dict[str, Any], timeout: float) -> Any:
    request = urllib.request.Request(url, data=json.dumps(body).encode(), headers=headers)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.load(response)


def validate_embedding(vector: Any) -> list[float]:
    if not isinstance(vector, list) or len(vector) != EMBEDDING_DIMENSIONS:
        raise EmbeddingError(f"임베딩은 {EMBEDDING_DIMENSIONS}차원이어야 합니다.")
    if not all(type(value) in (int, float) and math.isfinite(value) for value in vector):
        raise EmbeddingError("임베딩에 유한하지 않거나 숫자가 아닌 값이 있습니다.")
    if not any(vector):
        raise EmbeddingError("영벡터 임베딩은 사용할 수 없습니다.")
    return [float(value) for value in vector]


def embed_texts(
    texts: list[str],
    *,
    settings: Settings | None = None,
    post: EmbeddingPost = _post_json,
) -> list[list[float]]:
    """입력 순서대로 검증된 벡터를 돌려준다. 하나라도 잘못되면 전체를 실패시킨다."""
    if not texts:
        return []
    settings = settings or load_settings()
    if not (settings.embedding_api_url and settings.embedding_api_key and settings.embedding_model):
        raise EmbeddingError("EMBEDDING_API_URL·EMBEDDING_API_KEY·EMBEDDING_MODEL을 설정해야 합니다.")

    headers = {
        "Authorization": f"Bearer {settings.embedding_api_key}",
        "Content-Type": "application/json",
    }
    body = {"model": settings.embedding_model, "input": list(texts)}
    try:
        data = post(settings.embedding_api_url, headers, body, settings.embedding_timeout_seconds)
    except Exception as exc:
        # urllib 오류 메시지에는 키가 없지만, 원인 문자열을 그대로 싣지 않는다.
        raise EmbeddingError(f"임베딩 API 호출 실패: {type(exc).__name__}") from None

    if not isinstance(data, Mapping) or not isinstance(data.get("data"), list):
        raise EmbeddingError("임베딩 응답 구조가 올바르지 않습니다.")
    model = data.get("model")
    if model is not None and model != settings.embedding_model:
        raise EmbeddingError("요청한 임베딩 모델과 응답 모델이 다릅니다.")

    vectors: dict[int, list[float]] = {}
    for item in data["data"]:
        if not isinstance(item, Mapping) or "embedding" not in item:
            raise EmbeddingError("임베딩 응답 구조가 올바르지 않습니다.")
        index = item.get("index")
        if type(index) is not int or not 0 <= index < len(texts) or index in vectors:
            raise EmbeddingError("임베딩 응답 순번이 올바르지 않습니다.")
        vectors[index] = validate_embedding(item["embedding"])
    if len(vectors) != len(texts):
        raise EmbeddingError("임베딩 응답 개수가 입력과 다릅니다.")
    return [vectors[i] for i in range(len(texts))]


def pattern_embedding_text(pattern: Mapping[str, Any]) -> str:
    """수법 카드를 임베딩할 문구로 만든다. 비어 있는 항목은 뺀다."""
    lines = [f"수법: {pattern['name'].strip()}"]
    for label, key in (("설명", "summary"), ("사칭 대상", "impersonation"), ("유도 행동", "lure_action")):
        value = (pattern.get(key) or "").strip()
        if value:
            lines.append(f"{label}: {value}")
    triggers = [t.strip() for t in pattern.get("triggers") or [] if t and t.strip()]
    if triggers:
        lines.append("위험 신호: " + ", ".join(triggers))
    examples = [
        (example.get("text") or "").strip()
        for example in pattern.get("example_messages") or []
        if isinstance(example, Mapping)
    ]
    examples = [text for text in examples if text]
    if examples:
        lines.append("예시 문자:")
        lines.extend(f"- {text}" for text in examples)
    return "\n".join(lines)
