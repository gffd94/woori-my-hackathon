from datetime import datetime
from types import SimpleNamespace
from typing import get_args

import pytest
from pydantic import ValidationError

from app.domain.enums import CaseStatus, Category
from app.schemas.analyze import AnalyzeRequest, AnalyzeResponse
from app.schemas.case import CaseListResponse, CaseOut, CaseStatusUpdate, CaseUpdateResult
from app.schemas.report import ReportRequest, ReportResponse
from app.services.decision import FinalDecision


# --- 공통 Enum (SPEC 2.5.2, 2.11) ---

def test_사례_상태와_카테고리_값은_SPEC과_같다():
    assert [s.value for s in CaseStatus] == ["pending", "verified", "rejected"]
    assert [c.value for c in Category] == ["finance", "delivery", "public_agency", "job", "other"]


# --- 판별 요청 (SPEC 2.11: 공백만 금지, 최대 5,000자, 추가 필드 거부) ---

def test_판별_요청은_앞뒤_공백을_제거한다():
    request = AnalyzeRequest(message="  [가상은행] 계좌가 정지되었습니다  ")

    assert request.message == "[가상은행] 계좌가 정지되었습니다"


@pytest.mark.parametrize("message", ["", "   ", "a" * 5001])
def test_판별_요청은_빈_문자와_5000자_초과를_거부한다(message):
    with pytest.raises(ValidationError):
        AnalyzeRequest(message=message)


def test_판별_요청은_5000자까지_받는다():
    assert len(AnalyzeRequest(message="a" * 5000).message) == 5000


def test_판별_요청은_정의되지_않은_필드를_거부한다():
    with pytest.raises(ValidationError):
        AnalyzeRequest(message="문자", category="finance")


# --- 판별 응답 ---

COMPLETED_RETRIEVAL = {"status": "completed", "method": "hybrid", "coverage": "complete", "reason_code": None}


def test_판별_응답은_SPEC_필드만_내보내고_내부용_필드는_뺀다():
    internal = {
        "status": "RISK",
        "risk_level": "high",
        "reasons": ["신고된 악성 URL이 포함되어 있습니다"],
        "matched_cases": 3,
        "guide_type": "damage_stage",
        "retrieval": COMPLETED_RETRIEVAL,
        "register_as_pending": True,
        "score": 0.9,
        "source": "paste",
    }

    body = AnalyzeResponse.model_validate(internal).model_dump(mode="json")

    assert body == {
        "status": "RISK",
        "risk_level": "high",
        "reasons": ["신고된 악성 URL이 포함되어 있습니다"],
        "matched_cases": 3,
        "guide_type": "damage_stage",
        "retrieval": COMPLETED_RETRIEVAL,
        "evidence": [],
    }


def test_검색_미완료면_matched_cases는_null이다():
    body = AnalyzeResponse(
        status="UNKNOWN",
        risk_level="unknown",
        reasons=[],
        matched_cases=None,
        guide_type="verification",
        retrieval={"status": "failed", "method": None, "coverage": "unknown"},
    ).model_dump(mode="json")

    assert body["matched_cases"] is None
    assert body["retrieval"] == {"status": "failed", "method": None, "coverage": "unknown", "reason_code": None}


@pytest.mark.parametrize("retrieval", [
    {"status": "done", "method": "hybrid", "coverage": "complete"},
    {"status": "completed", "method": "vector", "coverage": "complete"},
    {"status": "completed", "method": "hybrid", "coverage": "full"},
])
def test_검색_상태는_SPEC_값만_허용한다(retrieval):
    with pytest.raises(ValidationError):
        AnalyzeResponse(status="UNKNOWN", risk_level="unknown", reasons=[], matched_cases=None,
                        guide_type="verification", retrieval=retrieval)


@pytest.mark.parametrize("guide_type", ["verify_first", "none"])
def test_예전_안내_유형은_거부한다(guide_type):
    with pytest.raises(ValidationError):
        AnalyzeResponse(status="UNKNOWN", risk_level="unknown", reasons=[], matched_cases=None,
                        guide_type=guide_type, retrieval=COMPLETED_RETRIEVAL)


@pytest.mark.parametrize("field", ["risk_level", "guide_type"])
def test_판별_응답의_값_목록은_FinalDecision과_같다(field):
    # decision.py에 값이 추가되면 응답 변환에서 오류가 나므로 여기서 먼저 잡는다
    response_values = get_args(AnalyzeResponse.model_fields[field].annotation)
    decision_values = get_args(FinalDecision.model_fields[field].annotation)

    assert set(response_values) == set(decision_values)


# --- 신고 (SPEC 1.4, 2.11) ---

def test_신고_요청은_카테고리를_생략하면_other다():
    assert ReportRequest(message="택배 주소 확인 http://fake.example").category == Category.OTHER


@pytest.mark.parametrize("category", ["finance", "delivery", "public_agency", "job", "other"])
def test_신고_요청은_SPEC_카테고리를_받는다(category):
    assert ReportRequest(message="문자", category=category).category.value == category


@pytest.mark.parametrize("category", ["택배", "FINANCE", "", "  ", None])
def test_신고_요청은_그_외_카테고리를_거부한다(category):
    with pytest.raises(ValidationError):
        ReportRequest(message="문자", category=category)


def test_신고_요청도_빈_문자와_추가_필드를_거부한다():
    with pytest.raises(ValidationError):
        ReportRequest(message="   ")
    with pytest.raises(ValidationError):
        ReportRequest(message="문자", status="verified")


def test_신고_응답은_id_status_report_count다():
    response = ReportResponse(id=1, status="pending", report_count=2)

    assert response.model_dump(mode="json") == {"id": 1, "status": "pending", "report_count": 2}


@pytest.mark.parametrize("fields", [{"id": 0}, {"report_count": 0}, {"status": "deleted"}])
def test_신고_응답은_양수_id와_1이상_신고수와_정해진_상태만_허용한다(fields):
    with pytest.raises(ValidationError):
        ReportResponse(**({"id": 1, "status": "pending", "report_count": 1} | fields))


# --- 관리자 변경 (SPEC 1.5.3: status + expected_version만) ---

@pytest.mark.parametrize("status", ["verified", "rejected"])
def test_관리자_처리는_verified와_rejected만_받는다(status):
    assert CaseStatusUpdate(status=status, expected_version=1).status == status


@pytest.mark.parametrize("status", ["pending", "VERIFIED", "deleted"])
def test_관리자_처리는_그_외_상태를_거부한다(status):
    with pytest.raises(ValidationError):
        CaseStatusUpdate(status=status, expected_version=1)


@pytest.mark.parametrize("body", [{}, {"expected_version": 0}, {"expected_version": -1}, {"expected_version": "abc"}])
def test_관리자_처리는_양의_정수_expected_version이_필수다(body):
    with pytest.raises(ValidationError):
        CaseStatusUpdate(status="verified", **body)


def test_관리자_처리는_category_같은_추가_필드를_거부한다():
    with pytest.raises(ValidationError):
        CaseStatusUpdate(status="verified", expected_version=1, category="finance")


# --- 관리자 목록·사례 응답 ---

def _orm_case(**overrides):
    data = dict(
        id=7,
        message_text="[가상은행] ***님 계좌가 정지되었습니다",
        embedding=[0.1] * 1536,
        category="finance",
        status="pending",
        report_count=4,
        created_at=datetime(2026, 10, 26, 12, 0),
    )
    data.update(overrides)
    return SimpleNamespace(**data)


def test_사례_응답은_ORM_객체에서_만들고_임베딩은_뺀다():
    body = CaseOut.model_validate(_orm_case()).model_dump(mode="json")

    assert "embedding" not in body
    assert body["id"] == 7
    assert body["status"] == "pending"
    assert body["category"] == "finance"
    assert body["report_count"] == 4


def test_목록_응답은_items_limit_offset으로_감싼다():
    body = CaseListResponse(
        items=[CaseOut.model_validate(_orm_case())], limit=20, offset=0
    ).model_dump(mode="json")

    assert set(body) == {"items", "limit", "offset"}
    assert [item["id"] for item in body["items"]] == [7]


def test_관리자_처리_결과는_사례_응답과_같은_형식이다():
    result = CaseUpdateResult.model_validate(_orm_case(status="verified"))

    assert result.status == CaseStatus.VERIFIED
