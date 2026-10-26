"""여러 schema에서 같이 쓰는 입력 규칙"""

from typing import Annotated

from pydantic import BeforeValidator, StringConstraints

MAX_MESSAGE_CHARS = 2000

# 판별·신고에 공통으로 쓰는 문자 원문. 앞뒤 공백을 지운 뒤 길이를 검사한다.
MessageText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_MESSAGE_CHARS),
]


def _blank_to_none(v: object) -> object:
    if isinstance(v, str):
        return v.strip() or None
    return v


# 선택 입력 분류. 빈 문자열은 "입력 안 함"으로 본다.
# TODO: DB 담당자와 category 목록을 정하면 Enum으로 교체
Category = Annotated[str | None, BeforeValidator(_blank_to_none)]
