"""POST /analyze 요청·응답"""

from typing import Literal

from pydantic import BaseModel

from app.schemas.common import MessageText, StrictRequest
from app.services.decision import Status


class AnalyzeRequest(StrictRequest):
    message: MessageText
    source: Literal["share", "paste"] = "paste"


class AnalyzeResponse(BaseModel):
    """DecisionResult에서 화면에 필요한 필드만 내보낸다 (register_as_pending 같은 내부용 필드는 무시)."""

    status: Status
    # 값 목록은 DecisionResult와 같아야 한다 (tests/test_schemas.py에서 확인)
    # TODO: SPEC 2.10의 prevention/verification은 decision.py SAFE 조건 수정 때 함께 반영
    risk_level: Literal["high", "low", "unknown"]
    reasons: list[str] = []
    matched_cases: int = 0
    guide_type: Literal["damage_stage", "verify_first", "none"]
