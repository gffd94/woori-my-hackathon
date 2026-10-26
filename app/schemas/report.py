"""POST /reports 요청·응답"""

from pydantic import BaseModel

from app.schemas.common import Category, MessageText


class ReportRequest(BaseModel):
    message: MessageText
    category: Category = None


class ReportResponse(BaseModel):
    case_id: int
    # TODO: DB 담당자와 CaseStatus Enum을 정하면 교체
    status: str
    report_count: int
    # False면 비슷한 기존 사례에 합쳐져 report_count만 올라간 것
    is_new: bool
