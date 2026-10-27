"""POST /reports 요청·응답"""

from pydantic import BaseModel, PositiveInt

from app.domain.enums import CaseStatus, Category
from app.schemas.common import MessageText, StrictRequest


class ReportRequest(StrictRequest):
    message: MessageText
    category: Category = Category.OTHER


class ReportResponse(BaseModel):
    id: PositiveInt
    status: CaseStatus
    report_count: PositiveInt
