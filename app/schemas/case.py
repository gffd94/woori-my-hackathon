"""GET·PATCH /admin/cases 요청·응답"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, PositiveInt

from app.domain.enums import CaseStatus, Category
from app.schemas.common import StrictRequest


class CaseOut(BaseModel):
    """cases 행을 그대로 받아 만든다. embedding은 내보내지 않는다.

    TODO: ERD 확정 후 컬럼 이름(masked_message 등)과 version·updated_at 반영
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    message_text: str
    category: Category
    status: CaseStatus
    report_count: int
    created_at: datetime


class CaseListResponse(BaseModel):
    items: list[CaseOut]
    limit: int
    offset: int


class CaseStatusUpdate(StrictRequest):
    # 관리자는 pending을 검증 완료나 반려로만 바꿀 수 있다
    status: Literal["verified", "rejected"]
    # 목록에서 받은 version. 현재 DB version과 다르면 409
    expected_version: PositiveInt


class CaseUpdateResult(CaseOut):
    """PATCH 성공 시 돌려주는 업데이트된 사례"""
