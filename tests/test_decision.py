import pytest

from app.services.decision import EntityMatch, Status, decide
from app.services.extractor import extract
from app.services.llm_judge import LLMJudgement, Signal


def _judgement(suspicious=False, signals=None, reasons=None):
    return LLMJudgement(
        suspicious=suspicious,
        signals=[Signal(signal=name, evidence=evidence) for name, evidence in signals or []],
        reasons=reasons if reasons is not None else (["근거"] if suspicious or signals else []),
    )


def _decide(message, matches, judgement, matched_cases=0):
    return decide(matches, judgement, matched_cases, extracted=extract(message), message=message)


def _assert_risk(result, level):
    assert result.status == Status.RISK
    assert result.risk_level == level
    assert result.guide_type == ("damage_stage" if level == "high" else "verification")


OFFICIAL_DOMAIN = [EntityMatch(value="official.example", type="domain", label="official")]


def test_scam_요소가_있으면_LLM_결과와_관계없이_RISK_high():
    matches = [EntityMatch(value="http://scam.example", type="url", label="scam")]

    result = _decide("http://scam.example 확인", matches, judgement=None)

    _assert_risk(result, "high")
    assert result.register_as_pending is False


def test_가상은행_계좌정지_외부링크는_RISK_high():
    message = "[가상은행] 계좌가 정지되었습니다 https://fake.example"
    judgement = _judgement(True, [("기관 사칭", "[가상은행]"), ("비공식 URL", "https://fake.example")])

    result = _decide(message, [], judgement, matched_cases=3)

    _assert_risk(result, "high")
    assert result.matched_cases == 3
    assert "기관 사칭 신호가 확인되었습니다" in result.reasons


def test_DB에_없는_신규_기관_사칭은_RISK이고_pending_등록_대상():
    message = "가상기관입니다 본인 인증을 진행하세요"
    result = _decide(message, [], _judgement(True, [("기관 사칭", "가상기관입니다"), ("인증 요구", "본인 인증")]))

    _assert_risk(result, "high")
    assert result.register_as_pending is True


def test_U39_강한_신호_1개면_high():
    result = _decide("본인 인증을 진행하세요", [], _judgement(False, [("인증 요구", "본인 인증")]))

    _assert_risk(result, "high")


def test_U40_약한_신호_2개면_high():
    message = "오늘 안에 꼭 답장 부탁드립니다"
    signals = [("긴급성 압박", "오늘 안에"), ("답장·회신 유도", "답장 부탁드립니다")]

    _assert_risk(_decide(message, [], _judgement(False, signals)), "high")


def test_U35_약한_신호_1개만_있으면_low():
    message = "확인 후 이 문자에 답장 부탁드립니다"
    result = _decide(message, [], _judgement(False, [("답장·회신 유도", "답장 부탁드립니다")]))

    _assert_risk(result, "low")


def test_목록에_없는_신호는_약한_신호로_센다():
    message = "가상 이벤트 당첨 안내입니다"

    _assert_risk(_decide(message, [], _judgement(False, [("경품 당첨 미끼", "이벤트 당첨")])), "low")


def test_U37_신호_없이_LLM이_의심만_하면_low():
    # 공식 링크가 있는 문자다. 링크·번호가 아예 없으면 U37b처럼 SAFE다 (SPEC 2.10.1).
    message = "가상 안내 문구입니다 https://official.example"
    result = _decide(message, OFFICIAL_DOMAIN, _judgement(True, [], reasons=[]))

    _assert_risk(result, "low")
    assert result.reasons


def test_U37b_링크_번호가_없고_신호_없이_LLM이_의심만_하면_SAFE():
    result = _decide("가상 안내 문구입니다", [], _judgement(True, [], reasons=[]))

    assert result.status == Status.SAFE


def test_U41_미확인_URL과_약한_신호가_함께_있으면_high():
    message = "주소 확인 https://unseen.example"

    _assert_risk(_decide(message, [], _judgement(False, [("비공식 URL", "https://unseen.example")])), "high")


def test_U42_미확인_URL과_LLM_의심이_함께_있으면_high():
    _assert_risk(_decide("주소 확인 https://unseen.example", [], _judgement(True, [])), "high")


def test_official_일치이고_위험_신호가_없으면_SAFE():
    result = _decide("가상은행 결제 안내 https://official.example", OFFICIAL_DOMAIN, _judgement(False))

    assert result.status == Status.SAFE
    assert result.risk_level == "low"
    assert result.guide_type == "prevention"
    assert result.reasons == ["위험 신호가 발견되지 않았습니다"]


def test_official_전화번호만_있고_신호가_없으면_SAFE():
    matches = [EntityMatch(value="15880000", type="phone", label="official")]

    assert _decide("문의 1588-0000", matches, _judgement(False)).status == Status.SAFE


def test_official_일치여도_강한_신호가_있으면_high():
    message = "https://official.example 이 번호로 연락 주세요"
    result = _decide(message, OFFICIAL_DOMAIN, _judgement(False, [("개인 번호로 연락 유도", "이 번호로 연락")]))

    _assert_risk(result, "high")


def test_U25_공식_URL과_미확인_URL만_있으면_low():
    message = "https://official.example 및 https://unseen.example 안내"
    result = _decide(message, OFFICIAL_DOMAIN, _judgement(False))

    _assert_risk(result, "low")
    assert any("확인되지 않은" in reason for reason in result.reasons)


def test_U31_공식_host라도_미확인_전화번호가_있으면_RISK():
    message = "https://official.example 문의 010-0000-0000"

    _assert_risk(_decide(message, OFFICIAL_DOMAIN, _judgement(False)), "low")


def test_공식_host에_기본이_아닌_포트가_있으면_공식으로_확인하지_않는다():
    message = "https://official.example:8443/notice 안내"

    _assert_risk(_decide(message, OFFICIAL_DOMAIN, _judgement(False)), "low")


def test_U28_링크_번호_신호가_모두_없으면_SAFE():
    result = _decide("오늘 저녁 7시에 가상역에서 보자", [], _judgement(False))

    assert result.status == Status.SAFE
    assert result.guide_type == "prevention"


@pytest.mark.parametrize("signals", [[], [("지인·가족 사칭", "엄마 나 폰 액정")]])
def test_U33_U34_가족_사칭은_신호나_규칙으로_high(signals):
    message = "엄마 나 폰 액정 깨져서 수리 맡겼어 이 번호로 문자 줘"

    result = _decide(message, [], _judgement(False, signals))

    _assert_risk(result, "high")
    if not signals:
        assert any("가족 사칭" in reason for reason in result.reasons)


def test_LLM_오류는_official_일치여도_SAFE로_새지_않는다():
    result = _decide("https://official.example", OFFICIAL_DOMAIN, judgement=None)

    assert result.status == Status.UNKNOWN
    assert result.risk_level == "unknown"
    assert result.guide_type == "verification"


def test_불완전_추출은_신호가_없어도_UNKNOWN():
    result = _decide("https://notice.example:wrong 안내", [], _judgement(False))

    assert result.status == Status.UNKNOWN
