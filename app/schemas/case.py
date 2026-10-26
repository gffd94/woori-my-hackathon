"""GET·PATCH /admin/cases 요청·응답"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.schemas.common import Category


class CaseOut(BaseModel):
    """cases 행을 그대로 받아 만든다. embedding은 내보내지 않는다."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    message_text: str
    category: str | None = None
    # TODO: DB 담당자와 CaseStatus Enum을 정하면 교체
    status: str
    report_count: int
    created_at: datetime


class CaseStatusUpdate(BaseModel):
    # 관리자는 pending을 검증 완료나 반려로만 바꿀 수 있다
    status: Literal["verified", "rejected"]
    category: Category = None


class CaseUpdateResult(CaseOut):
    # verified 처리로 entities에 scam으로 새로 추가된 URL·번호 수
    added_entities: int = 0
