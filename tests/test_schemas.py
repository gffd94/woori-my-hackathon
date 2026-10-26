from datetime import datetime
from types import SimpleNamespace
from typing import get_args

import pytest
from pydantic import ValidationError

from app.schemas.analyze import AnalyzeRequest, AnalyzeResponse
from app.schemas.case import CaseOut, CaseStatusUpdate, CaseUpdateResult
from app.schemas.report import ReportRequest, ReportResponse
from app.services.decision import DecisionResult, Status


# --- 판별 요청 ---

def test_판별_요청은_앞뒤_공백을_제거한다():
    request = AnalyzeRequest(message="  [가상은행] 계좌가 정지되었습니다  ")

    assert request.message == "[가상은행] 계좌가 정지되었습니다"


@pytest.mark.parametrize("message", ["", "   ", "a" * 2001])
def test_판별_요청은_빈_문자와_2000자_초과를_거부한다(message):
    with pytest.raises(ValidationError):
        AnalyzeRequest(message=message)


def test_판별_요청은_2000자까지_받는다():
    assert len(AnalyzeRequest(message="a" * 2000).message) == 2000


# --- 판별 응답 ---

def test_판별_응답은_DecisionResult에서_만들고_내부용_필드는_뺀다():
    result = DecisionResult(
        status=Status.RISK,
        risk_level="high",
        reasons=["금융기관 사칭", "비공식 URL 포함"],
        matched_cases=3,
        guide_type="damage_stage",
        register_as_pending=True,
    )

    body = AnalyzeResponse.model_validate(result.model_dump()).model_dump(mode="json")

    assert body == {
        "status": "RISK",
        "risk_level": "high",
        "reasons": ["금융기관 사칭", "비공식 URL 포함"],
        "matched_cases": 3,
        "guide_type": "damage_stage",
    }


@pytest.mark.parametrize("field", ["risk_level", "guide_type"])
def test_판별_응답의_값_목록은_DecisionResult와_같다(field):
    # decision.py에 값이 추가되면 응답 변환에서 오류가 나므로 여기서 먼저 잡는다
    response_values = get_args(AnalyzeResponse.model_fields[field].annotation)
    decision_values = get_args(DecisionResult.model_fields[field].annotation)

    assert set(response_values) == set(decision_values)


# --- 신고 ---

def test_신고_요청은_분류를_생략할_수_있다():
    request = ReportRequest(message="택배 주소 확인 http://fake.example")

    assert request.category is None


def test_신고_요청의_빈_분류는_None으로_본다():
    assert ReportRequest(message="문자", category="  ").category is None


def test_신고_요청도_빈_문자를_거부한다():
    with pytest.raises(ValidationError):
        ReportRequest(message="   ")


def test_신고_응답():
    response = ReportResponse(case_id=1, status="pending", report_count=2, is_new=False)

    assert response.model_dump() == {"case_id": 1, "status": "pending", "report_count": 2, "is_new": False}


# --- 관리자 ---

@pytest.mark.parametrize("status", ["verified", "rejected"])
def test_관리자_처리는_verified와_rejected만_받는다(status):
    assert CaseStatusUpdate(status=status).status == status


@pytest.mark.parametrize("status", ["pending", "VERIFIED", "deleted"])
def test_관리자_처리는_그_외_상태를_거부한다(status):
    with pytest.raises(ValidationError):
        CaseStatusUpdate(status=status)


def test_관리자_처리의_빈_분류는_None으로_본다():
    # 빈 문자열로 기존 분류를 덮어쓰지 않도록
    assert CaseStatusUpdate(status="verified", category="  ").category is None
    assert CaseStatusUpdate(status="verified", category=" 택배 ").category == "택배"


def _orm_case(**overrides):
    data = dict(
        id=7,
        message_text="[가상은행] ***님 계좌가 정지되었습니다",
        embedding=[0.1] * 1536,
        category="기관 사칭",
        status="pending",
        report_count=4,
        created_at=datetime(2026, 10, 26, 12, 0),
    )
    data.update(overrides)
    return SimpleNamespace(**data)


def test_사례_응답은_ORM_객체에서_만들고_임베딩은_뺀다():
    body = CaseOut.model_validate(_orm_case()).model_dump()

    assert "embedding" not in body
    assert body["id"] == 7
    assert body["status"] == "pending"
    assert body["report_count"] == 4


def test_관리자_처리_결과에는_추가된_entities_수가_있다():
    result = CaseUpdateResult.model_validate(_orm_case(status="verified"))

    assert result.added_entities == 0
    assert CaseUpdateResult(**result.model_dump() | {"added_entities": 2}).added_entities == 2
