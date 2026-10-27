import json

import pytest

from app.services.llm_judge import SIGNALS, SYSTEM_PROMPT, LLMJudgement, judge, parse_judgement

MESSAGE = "[가상은행] 계좌가 정지되었습니다 http://fake.example"


def _valid_raw(**overrides):
    data = {
        "suspicious": True,
        "signals": [
            {"signal": "기관 사칭", "evidence": "[가상은행]"},
            {"signal": "비공식 URL", "evidence": "http://fake.example"},
        ],
        "reasons": ["은행을 사칭하며 외부 링크 접속을 유도함"],
        "category": "기관 사칭",
    }
    data.update(overrides)
    return json.dumps(data, ensure_ascii=False)


def test_정상_JSON은_LLMJudgement로_파싱된다():
    result = parse_judgement(_valid_raw())

    assert isinstance(result, LLMJudgement)
    assert result.suspicious is True
    assert [s.signal for s in result.signals] == ["기관 사칭", "비공식 URL"]
    assert result.signals[0].evidence == "[가상은행]"


def test_JSON이_아니면_None():
    assert parse_judgement("위험해 보입니다.") is None


def test_필수_필드가_빠지면_None():
    assert parse_judgement(json.dumps({"signals": []})) is None


def test_정의되지_않은_필드가_있으면_None():
    assert parse_judgement(_valid_raw(score=0.9)) is None


def test_예전_형식의_응답은_None():
    old = json.dumps({"is_high_risk": True, "signals": ["기관 사칭"], "reasons": [], "category": None})
    assert parse_judgement(old) is None


def test_judge는_수법_카드를_참고용으로_프롬프트에_넣어_LLM을_호출한다():
    captured = {}

    def fake_llm(system, user):
        captured["user"] = user
        return _valid_raw()

    result = judge(MESSAGE, ["유사 사례 문구"], llm_call=fake_llm)

    assert result.suspicious is True
    assert "유사 사례 문구" in captured["user"]
    assert "참고용" in captured["user"]
    assert "계좌가 정지되었습니다" in captured["user"]


def test_U36_근거_문구가_문자에_없는_신호는_버린다():
    raw = _valid_raw(signals=[
        {"signal": "기관 사칭", "evidence": "[가상은행]"},
        {"signal": "앱 설치 유도", "evidence": "앱을 설치하세요"},
        {"signal": "긴급성 압박", "evidence": ""},
    ])

    result = judge(MESSAGE, [], llm_call=lambda s, u: raw)

    assert [s.signal for s in result.signals] == ["기관 사칭"]


def test_근거_문구는_공백과_전각_문자_차이를_무시하고_확인한다():
    raw = _valid_raw(signals=[{"signal": "비공식 URL", "evidence": "ＨＴＴＰ://fake. example"}])

    result = judge(MESSAGE, [], llm_call=lambda s, u: raw)

    assert [s.signal for s in result.signals] == ["비공식 URL"]


def test_같은_신호는_한_번만_센다():
    raw = _valid_raw(signals=[
        {"signal": "기관 사칭", "evidence": "[가상은행]"},
        {"signal": "기관 사칭", "evidence": "계좌가 정지"},
    ])

    result = judge(MESSAGE, [], llm_call=lambda s, u: raw)

    assert [s.signal for s in result.signals] == ["기관 사칭"]


@pytest.mark.parametrize("signal", ["지인·가족 사칭", "금전·상품권 요청", "전화 연락 유도", "답장·회신 유도"])
def test_시스템_프롬프트에_새_신호가_있다(signal):
    assert signal in SIGNALS
    assert signal in SYSTEM_PROMPT


def test_시스템_프롬프트는_주제만으로_신호를_세지_않게_한다():
    assert "주제" in SYSTEM_PROMPT
    assert "evidence" in SYSTEM_PROMPT
    assert "suspicious" in SYSTEM_PROMPT


def test_시스템_프롬프트는_발신_표기만으로_기관_사칭을_세지_않게_한다():
    assert "발신 표기" in SYSTEM_PROMPT


def test_LLM_응답_형식_오류면_None():
    result = judge("아무 문자", [], llm_call=lambda s, u: "{broken json")

    assert result is None


def test_LLM_API_오류면_None():
    def raising_llm(system, user):
        raise TimeoutError("API timeout")

    assert judge("아무 문자", [], llm_call=raising_llm) is None
