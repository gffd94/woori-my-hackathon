"""SPEC 2.10 최종 판정 (3.4 D·F 사례, 3.4.2 SAFE 조건별 차단)."""

from dataclasses import replace

import pytest

from app.services.decision import (
    REASON_CONFLICT,
    REASON_PROCESSING_FAILED,
    REASON_RETRIEVAL_INCOMPLETE,
    REASON_SAFE,
    REASON_UNRESOLVED,
    Evidence,
    Status,
    decide_final,
)
from app.services.llm_judge import LLMJudgement, Signal


def _llm(suspicious=False, signals=(), suggestion=None, reasons=("LLM이 쓴 자유 문장",)):
    # decide_final은 judge()가 근거 문구를 확인한 신호를 받는다. 여기서는 신호 이름을 근거로 쓴다.
    return LLMJudgement(
        suspicious=suspicious,
        signals=[Signal(signal=name, evidence=name) for name in signals],
        reasons=list(reasons),
        suggestion=suggestion,
    )


CLEAR_RISK = _llm(True, ["기관 사칭", "비공식 URL"], "RISK")
SAFE_LLM = _llm(False, [], "SAFE", reasons=())

# SAFE가 가능한 기준 입력. 아래 테스트는 조건을 하나씩 깨서 SAFE가 막히는지 본다.
SAFE_BASE = Evidence(
    processing_failed=False,
    retrieval_complete=True,
    judgement=SAFE_LLM,
    official_support=True,
)


def _level(result):
    return (result.status, result.risk_level, result.guide_type)


def test_판정별_위험수준과_안내유형이_SPEC과_같다():
    risk = decide_final(replace(SAFE_BASE, malicious_types=frozenset({"url"})))
    caution = decide_final(replace(SAFE_BASE, unresolved=True))
    safe = decide_final(SAFE_BASE)
    unknown = decide_final(replace(SAFE_BASE, processing_failed=True))

    assert _level(risk) == (Status.RISK, "high", "damage_stage")
    assert _level(caution) == (Status.RISK, "low", "verification")
    assert _level(safe) == (Status.SAFE, "low", "prevention")
    assert _level(unknown) == (Status.UNKNOWN, "unknown", "verification")


# --- 3.4.1 RISK·SAFE·UNKNOWN ---

def test_D01_악성_단서_일치는_RISK():
    result = decide_final(replace(SAFE_BASE, malicious_types=frozenset({"domain"})))

    assert _level(result)[:2] == (Status.RISK, "high")
    assert result.reasons == ["신고된 악성 도메인이 포함되어 있습니다"]


def test_D02_DB_미등록이어도_명확한_위험_신호면_RISK():
    result = decide_final(replace(SAFE_BASE, judgement=CLEAR_RISK, official_support=False))

    assert _level(result)[:2] == (Status.RISK, "high")


def test_D03_악성_공식_충돌은_RISK이고_충돌_이유를_포함한다():
    result = decide_final(replace(SAFE_BASE, conflict=True, malicious_types=frozenset({"domain"})))

    assert result.status == Status.RISK
    assert REASON_CONFLICT in result.reasons


def test_D04a_공식_도메인이어도_악성_URL_일치면_RISK():
    result = decide_final(replace(SAFE_BASE, malicious_types=frozenset({"url"})))

    assert result.status == Status.RISK


def test_D04b_D05_공식_정보와_미확인_요소만_있으면_RISK_low():
    result = decide_final(replace(SAFE_BASE, unresolved=True))

    assert _level(result)[:2] == (Status.RISK, "low")
    assert result.reasons == [REASON_UNRESOLVED]


def test_D06_요소도_위험신호도_없으면_공식근거_없이도_SAFE():
    result = decide_final(replace(SAFE_BASE, official_support=False, judgement=_llm(suggestion="UNKNOWN")))

    assert result.status == Status.SAFE
    assert result.reasons == [REASON_SAFE]


def test_D09_악성_일치는_LLM이_SAFE를_제안해도_RISK():
    result = decide_final(replace(SAFE_BASE, malicious_types=frozenset({"phone"}), judgement=SAFE_LLM))

    assert result.status == Status.RISK


def test_D10_기관_사칭이_다른_근거_없이_혼자면_RISK_low():
    # 공식 링크로 뒷받침되지 않는 경우다. 공식 링크만 있으면 D10d처럼 SAFE다.
    result = decide_final(replace(SAFE_BASE, judgement=_llm(True, ["기관 사칭"]), official_support=False))

    assert _level(result)[:2] == (Status.RISK, "low")


def test_D10d_링크가_모두_공식이고_기관_사칭_신호만_있으면_SAFE():
    # 예: "[우리은행] ... https://wooribank.com" 정상 공지에 LLM이 발신 표기로 기관 사칭을 고른 경우
    result = decide_final(replace(SAFE_BASE, judgement=_llm(True, ["기관 사칭"], "RISK")))

    assert _level(result) == (Status.SAFE, "low", "prevention")
    assert result.reasons == [REASON_SAFE]


def test_D10e_공식_링크가_있어도_기관_사칭_외_신호가_섞이면_SAFE가_아니다():
    result = decide_final(replace(SAFE_BASE, judgement=_llm(True, ["기관 사칭", "긴급성 압박"])))

    assert result.status == Status.RISK


@pytest.mark.parametrize(
    "extra",
    [
        {"unresolved": True},                                              # 미확인 URL·전화번호
        {"judgement": _llm(True, ["기관 사칭", "긴급성 압박"])},           # 다른 신호
        {"rule_matches": ("기관 연락 유도",)},                             # 규칙 일치
    ],
)
def test_D10b_기관_사칭에_다른_근거가_있으면_RISK_high(extra):
    base = replace(SAFE_BASE, judgement=_llm(True, ["기관 사칭"]))

    assert _level(decide_final(replace(base, **extra)))[:2] == (Status.RISK, "high")


def test_D10c_기관_사칭_외_강한_신호는_혼자여도_RISK_high():
    result = decide_final(replace(SAFE_BASE, judgement=_llm(False, ["인증 요구"])))

    assert _level(result)[:2] == (Status.RISK, "high")


def test_D12_약한_신호_하나면_RISK_low():
    result = decide_final(replace(SAFE_BASE, judgement=_llm(False, ["답장·회신 유도"])))

    assert _level(result)[:2] == (Status.RISK, "low")


def test_D13_약한_신호_두개면_RISK_high():
    result = decide_final(replace(SAFE_BASE, judgement=_llm(False, ["긴급성 압박", "답장·회신 유도"])))

    assert _level(result)[:2] == (Status.RISK, "high")


def test_D14_미확인_요소와_LLM_의심이_함께면_RISK_high():
    result = decide_final(replace(SAFE_BASE, unresolved=True, judgement=_llm(True, [])))

    assert _level(result)[:2] == (Status.RISK, "high")


def test_D15_신호_없이_LLM_의심만_있으면_RISK_low():
    result = decide_final(replace(SAFE_BASE, judgement=_llm(True, [])))

    assert _level(result)[:2] == (Status.RISK, "low")


def test_D16_규칙_안전장치가_일치하면_RISK_high이고_규칙_이름을_이유에_넣는다():
    result = decide_final(replace(SAFE_BASE, rule_matches=("가족 사칭",)))

    assert _level(result)[:2] == (Status.RISK, "high")
    assert any("가족 사칭" in reason for reason in result.reasons)


def test_목록_밖_신호는_약한_신호로_세고_화면_이유로_내보내지_않는다():
    result = decide_final(replace(SAFE_BASE, judgement=_llm(False, ["목록 밖 표현"])))

    assert _level(result)[:2] == (Status.RISK, "low")
    assert all("목록 밖 표현" not in reason for reason in result.reasons)


def test_불완전_추출은_UNKNOWN():
    result = decide_final(replace(SAFE_BASE, incomplete=True))

    assert result.status == Status.UNKNOWN


# --- 3.4.2 SAFE 조건별 차단 ---

@pytest.mark.parametrize(
    "broken",
    [
        {"unresolved": True},                       # 미확인 요소 없음
        {"incomplete": True},                       # 전체 요소 평가 완료
        {"conflict": True},                         # 정보 충돌 없음
        {"malicious_types": frozenset({"url"})},    # 악성 일치 없음
        {"judgement": _llm(False, ["긴급성 압박"], "SAFE")},  # 위험 신호 없음
        {"judgement": _llm(True, [], "SAFE")},      # LLM 의심 판단 없음
        {"rule_matches": ("가족 사칭",)},           # 규칙 일치 없음
        {"retrieval_complete": False},              # 완전한 검색
        {"processing_failed": True},                # 필수 처리 성공
        {"judgement": None},                        # LLM 응답 검증 성공
    ],
)
def test_SAFE_조건이_하나라도_빠지면_SAFE가_아니다(broken):
    assert decide_final(replace(SAFE_BASE, **broken)).status != Status.SAFE


def test_SAFE_이유는_서버_고정_문구다():
    result = decide_final(replace(SAFE_BASE, judgement=_llm(False, [], "SAFE", reasons=["무시해야 할 문장"])))

    assert result.status == Status.SAFE
    assert "무시해야 할 문장" not in result.reasons


# --- 3.4.3 필수 처리 실패 우선순위 ---

def test_F01_악성_일치와_LLM_실패가_겹치면_악성_일치가_우선해_RISK():
    result = decide_final(replace(SAFE_BASE, malicious_types=frozenset({"url"}), judgement=None))

    assert _level(result)[:2] == (Status.RISK, "high")


def test_F02_충돌과_검색_제한이_겹치면_충돌이_우선해_RISK():
    result = decide_final(replace(SAFE_BASE, conflict=True, retrieval_complete=False))

    assert result.status == Status.RISK
    assert REASON_CONFLICT in result.reasons


def test_F03_명확한_위험과_DB_처리_실패가_겹치면_UNKNOWN():
    result = decide_final(replace(SAFE_BASE, judgement=CLEAR_RISK, processing_failed=True))

    assert result.status == Status.UNKNOWN
    assert result.reasons == [REASON_PROCESSING_FAILED]


def test_검색_제한은_UNKNOWN():
    result = decide_final(replace(SAFE_BASE, retrieval_complete=False))

    assert result.status == Status.UNKNOWN
    assert result.reasons == [REASON_RETRIEVAL_INCOMPLETE]


# --- 이유 문구 ---

def test_RISK_이유는_목록에_있는_신호만_고정_문구로_바꾼다():
    judgement = _llm(True, ["기관 사칭", "비공식 URL", "목록 밖 표현"], "RISK", reasons=["LLM 자유 문장"])

    result = decide_final(replace(SAFE_BASE, judgement=judgement, official_support=False))

    assert result.status == Status.RISK
    assert result.reasons == ["기관 사칭 신호가 확인되었습니다", "비공식 URL 신호가 확인되었습니다"]


def test_악성_유형이_여러개면_이유를_모두_중복없이_보여준다():
    result = decide_final(
        replace(SAFE_BASE, malicious_types=frozenset({"phone", "url"}), judgement=CLEAR_RISK)
    )

    assert result.reasons[:2] == [
        "신고된 악성 URL이 포함되어 있습니다",
        "신고된 악성 전화번호가 포함되어 있습니다",
    ]
    assert len(result.reasons) == len(set(result.reasons))
