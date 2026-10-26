import json

from app.services.llm_judge import LLMJudgement, judge, parse_judgement


def _valid_raw(**overrides):
    data = {
        "is_high_risk": True,
        "signals": ["기관 사칭", "비공식 URL"],
        "reasons": ["은행을 사칭하며 외부 링크 접속을 유도함"],
        "category": "기관 사칭",
    }
    data.update(overrides)
    return json.dumps(data, ensure_ascii=False)


def test_정상_JSON은_LLMJudgement로_파싱된다():
    result = parse_judgement(_valid_raw())

    assert isinstance(result, LLMJudgement)
    assert result.is_high_risk is True
    assert result.signals == ["기관 사칭", "비공식 URL"]


def test_JSON이_아니면_None():
    assert parse_judgement("위험해 보입니다.") is None


def test_필수_필드가_빠지면_None():
    assert parse_judgement(json.dumps({"signals": []})) is None


def test_judge는_유사_사례를_프롬프트에_넣어_LLM을_호출한다():
    captured = {}

    def fake_llm(system, user):
        captured["user"] = user
        return _valid_raw()

    result = judge("[가상은행] 계좌가 정지되었습니다 http://fake.example", ["유사 사례 문구"], llm_call=fake_llm)

    assert result.is_high_risk is True
    assert "유사 사례 문구" in captured["user"]
    assert "계좌가 정지되었습니다" in captured["user"]


def test_LLM_응답_형식_오류면_None():
    result = judge("아무 문자", [], llm_call=lambda s, u: "{broken json")

    assert result is None


def test_LLM_API_오류면_None():
    def raising_llm(system, user):
        raise TimeoutError("API timeout")

    assert judge("아무 문자", [], llm_call=raising_llm) is None
