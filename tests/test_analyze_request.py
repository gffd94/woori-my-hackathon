"""판별 요청의 공개 스키마 계약을 검증한다."""

import pytest
from pydantic import ValidationError


def test_source를_생략하면_paste다():
    from app.schemas.analyze import AnalyzeRequest

    assert AnalyzeRequest(message="가상 안내").source == "paste"


@pytest.mark.parametrize("source", ["share", "paste"])
def test_source는_허용된_입력_경로를_받는다(source):
    from app.schemas.analyze import AnalyzeRequest

    request = AnalyzeRequest(message="가상 안내", source=source)

    assert request.source == source


@pytest.mark.parametrize("source", [None, "", "SHARE", " paste ", 1, True, [], {}])
def test_source는_null과_허용되지_않은_값을_거부한다(source):
    from app.schemas.analyze import AnalyzeRequest

    with pytest.raises(ValidationError):
        AnalyzeRequest(message="가상 안내", source=source)


@pytest.mark.parametrize("message", ["", " \t\n", "가" * 5001, None, 1, True, [], {}])
def test_message는_빈값과_길이_초과와_다른_타입을_거부한다(message):
    from app.schemas.analyze import AnalyzeRequest

    with pytest.raises(ValidationError):
        AnalyzeRequest(message=message)


@pytest.mark.parametrize("message", ["가" * 5000, "  " + "가" * 5000 + " \t\n"])
def test_message는_기존대로_공백_제거_후_5000자를_허용한다(message):
    from app.schemas.analyze import AnalyzeRequest

    assert AnalyzeRequest(message=message).message == "가" * 5000


def test_필수_message_누락과_추가_필드는_거부한다():
    from app.schemas.analyze import AnalyzeRequest

    for body in ({"source": "paste"}, {"message": "가상 안내", "extra": "가상 값"}):
        with pytest.raises(ValidationError):
            AnalyzeRequest.model_validate(body)
