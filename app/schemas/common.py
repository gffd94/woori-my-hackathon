"""여러 schema에서 같이 쓰는 입력 규칙 (SPEC 2.11)"""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, StringConstraints

MAX_MESSAGE_CHARS = 5000

# 판별·신고에 공통으로 쓰는 문자 원문. 앞뒤 공백을 지운 뒤 길이를 검사한다.
MessageText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_MESSAGE_CHARS),
]


class StrictRequest(BaseModel):
    """요청 body 공통 설정. 정의되지 않은 필드가 오면 422로 거부한다."""

    model_config = ConfigDict(extra="forbid")
