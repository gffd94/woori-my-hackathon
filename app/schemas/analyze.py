"""POST /analyze 요청·응답"""

from typing import Literal

from pydantic import BaseModel

from app.schemas.common import MessageText, StrictRequest
from app.services.decision import GuideType, RiskLevel, Status


class AnalyzeRequest(StrictRequest):
    message: MessageText
    source: Literal["share", "paste"] = "paste"


class RetrievalInfo(BaseModel):
    """수법 검색 상태 (SPEC 2.7.4). reason_code 목록은 미확정이라 현재는 항상 null이다."""

    status: Literal["completed", "limited", "failed", "not_run"]
    method: Literal["hybrid", "ngram"] | None
    coverage: Literal["complete", "limited", "unknown"]
    reason_code: str | None = None


class AnalyzeResponse(BaseModel):
    """화면에 필요한 필드만 내보낸다. source·score·원문·내부 플래그는 넣지 않는다 (SPEC 2.11.2)."""

    status: Status
    # 값 목록은 decision.FinalDecision과 같아야 한다 (tests/test_schemas.py에서 확인)
    risk_level: RiskLevel
    reasons: list[str]
    matched_cases: int | None
    guide_type: GuideType
    retrieval: RetrievalInfo
