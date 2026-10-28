"""POST /analyze 요청·응답"""

from typing import Literal
from datetime import date
import ipaddress
from urllib.parse import urlsplit

from pydantic import BaseModel, Field, field_validator

from app.schemas.common import MessageText, StrictRequest
from app.services.decision import GuideType, RiskLevel, Status
from app.services.masking import mask_text


class ReferenceSource(BaseModel):
    title: str
    site: str | None = None
    url: str | None = None
    posted_date: date | None = None

    @field_validator('title', 'site')
    @classmethod
    def mask_metadata(cls, value):
        return mask_text(value)[:300] if value else value

    @field_validator('url', mode='before')
    @classmethod
    def public_reference(cls, value):
        if not isinstance(value, str) or any(c.isspace() or ord(c) < 32 for c in value):
            return None
        try:
            parts = urlsplit(value)
            host = parts.hostname or ''
            if parts.scheme != 'https' or parts.username is not None or not host or '.' not in host:
                return None
            if parts.port not in (None, 443) or host.endswith(('.localhost', '.local', '.internal')):
                return None
            try:
                ipaddress.ip_address(host)
                return None
            except ValueError:
                pass
            # 공개 자료의 게시글 ID 쿼리는 보존하되 인증용 주소는 노출하지 않는다.
            if any(key in parts.query.lower() for key in ('token', 'password', 'secret', 'auth', 'email')):
                return None
            return value
        except ValueError:
            return None


class AnalysisEvidence(BaseModel):
    kind: Literal['indicator_match', 'official_match', 'unverified', 'signal', 'pattern']
    title: str
    detail: str
    value: str | None = None
    sources: list[ReferenceSource] = Field(default_factory=list)


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
    """기존 판정과 마스킹한 근거·출처. 입력 원문·점수·내부 플래그는 제외한다."""

    status: Status
    # 값 목록은 decision.FinalDecision과 같아야 한다 (tests/test_schemas.py에서 확인)
    risk_level: RiskLevel
    reasons: list[str]
    matched_cases: int | None
    guide_type: GuideType
    retrieval: RetrievalInfo
    evidence: list[AnalysisEvidence] = Field(default_factory=list)
