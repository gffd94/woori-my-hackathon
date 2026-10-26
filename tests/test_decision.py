from app.services.decision import EntityMatch, Status, decide
from app.services.llm_judge import LLMJudgement


def _judgement(is_high_risk, signals=None):
    return LLMJudgement(
        is_high_risk=is_high_risk,
        signals=signals or [],
        reasons=["근거"] if is_high_risk else [],
    )


def test_scam_요소가_있으면_LLM_결과와_관계없이_RISK():
    matches = [EntityMatch(value="http://scam.example", type="url", label="scam")]

    result = decide(matches, judgement=None)

    assert result.status == Status.RISK
    assert result.risk_level == "high"
    assert result.register_as_pending is False


def test_가상은행_계좌정지_외부링크는_RISK():
    judgement = _judgement(True, ["기관 사칭", "비공식 URL"])

    result = decide([], judgement, matched_cases=3)

    assert result.status == Status.RISK
    assert result.matched_cases == 3
    assert result.reasons == ["근거"]
    assert result.guide_type == "damage_stage"


def test_DB에_없는_신규_기관_사칭은_RISK이고_pending_등록_대상():
    result = decide([], _judgement(True, ["기관 사칭", "인증 요구"]))

    assert result.status == Status.RISK
    assert result.register_as_pending is True


def test_official_일치이고_위험_신호가_없으면_SAFE():
    matches = [EntityMatch(value="1588-0000", type="phone", label="official")]

    result = decide(matches, _judgement(False))

    assert result.status == Status.SAFE


def test_official_일치여도_위험_신호가_있으면_SAFE가_아니다():
    matches = [EntityMatch(value="1588-0000", type="phone", label="official")]

    result = decide(matches, _judgement(False, ["개인 번호로 연락 유도"]))

    assert result.status == Status.UNKNOWN


def test_지원금_개인번호처럼_근거가_부족하면_UNKNOWN():
    result = decide([], _judgement(False, ["개인 휴대폰 번호"]))

    assert result.status == Status.UNKNOWN


def test_LLM_오류는_official_일치여도_SAFE로_새지_않는다():
    matches = [EntityMatch(value="1588-0000", type="phone", label="official")]

    result = decide(matches, judgement=None)

    assert result.status == Status.UNKNOWN
