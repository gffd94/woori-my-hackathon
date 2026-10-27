"""SPEC 2.10 최종 판정 (3.4 D·F 사례, 3.4.2 SAFE 조건별 차단)."""

from dataclasses import replace

import pytest

from app.services.decision import (
    REASON_CONFLICT,
    REASON_PROCESSING_FAILED,
    REASON_RETRIEVAL_INCOMPLETE,
    Evidence,
    Status,
    decide_final,
)
from app.services.llm_judge import LLMJudgement


def _llm(is_high_risk=False, signals=(), suggestion=None, reasons=("LLM이 쓴 자유 문장",)):
    return LLMJudgement(
        is_high_risk=is_high_risk, signals=list(signals), reasons=list(reasons), suggestion=suggestion
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


def test_판정별_위험수준과_안내유형이_SPEC과_같다():
    risk = decide_final(replace(SAFE_BASE, malicious_types=frozenset({"url"})))
    safe = decide_final(SAFE_BASE)
    unknown = decide_final(replace(SAFE_BASE, official_support=False))

    assert (risk.status, risk.risk_level, risk.guide_type) == (Status.RISK, "high", "damage_stage")
    assert (safe.status, safe.risk_level, safe.guide_type) == (Status.SAFE, "low", "prevention")
    assert (unknown.status, unknown.risk_level, unknown.guide_type) == (
        Status.UNKNOWN, "unknown", "verification"
    )


# --- 3.4.1 RISK·SAFE·UNKNOWN ---

def test_D01_악성_단서_일치는_RISK():
    result = decide_final(replace(SAFE_BASE, malicious_types=frozenset({"domain"})))

    assert result.status == Status.RISK
    assert result.reasons == ["신고된 악성 도메인이 포함되어 있습니다"]


def test_D02_DB_미등록이어도_명확한_위험_신호면_RISK():
    result = decide_final(replace(SAFE_BASE, judgement=CLEAR_RISK, official_support=False))

    assert result.status == Status.RISK


def test_D03_악성_공식_충돌은_RISK이고_충돌_이유를_포함한다():
    result = decide_final(replace(SAFE_BASE, conflict=True, malicious_types=frozenset({"domain"})))

    assert result.status == Status.RISK
    assert REASON_CONFLICT in result.reasons


def test_D04a_공식_도메인이어도_악성_URL_일치면_RISK():
    result = decide_final(replace(SAFE_BASE, malicious_types=frozenset({"url"})))

    assert result.status == Status.RISK


def test_D04b_공식_도메인에_의심_단서만_있으면_UNKNOWN():
    result = decide_final(replace(SAFE_BASE, unresolved=True))

    assert result.status == Status.UNKNOWN


def test_D05_공식_정보와_미확인_요소가_섞이면_UNKNOWN():
    result = decide_final(replace(SAFE_BASE, unresolved=True, judgement=_llm(suggestion="SAFE")))

    assert result.status == Status.UNKNOWN


def test_D06_요소도_위험신호도_공식근거도_없으면_UNKNOWN():
    result = decide_final(replace(SAFE_BASE, official_support=False, judgement=_llm(suggestion="UNKNOWN")))

    assert result.status == Status.UNKNOWN


def test_D09_악성_일치는_LLM이_SAFE를_제안해도_RISK():
    result = decide_final(replace(SAFE_BASE, malicious_types=frozenset({"phone"}), judgement=SAFE_LLM))

    assert result.status == Status.RISK


def test_D10_위험신호_하나뿐이면_사칭_RISK로_확정하지_않는다():
    result = decide_final(replace(SAFE_BASE, official_support=False, judgement=_llm(True, ["기관 사칭"])))

    assert result.status == Status.UNKNOWN


# --- 3.4.2 SAFE 조건별 차단 ---

@pytest.mark.parametrize(
    "broken",
    [
        {"unresolved": True},                       # 전체 요소 평가 완료 / 미확인 요소 없음
        {"official_support": False},                # 충분한 공식 근거
        {"conflict": True},                         # 정보 충돌 없음
        {"malicious_types": frozenset({"url"})},    # 악성 일치 없음
        {"judgement": _llm(False, ["긴급성 압박"], "SAFE")},  # 의심·위험 신호 없음
        {"judgement": _llm(True, [], "SAFE")},      # LLM 고위험 표시
        {"retrieval_complete": False},              # 완전한 검색
        {"processing_failed": True},                # 필수 처리 성공
        {"judgement": None},                        # LLM 응답 검증 성공
        {"judgement": _llm(False, [], None)},       # 명시적 SAFE 제안 (is_high_risk=false만으로는 아님)
        {"judgement": _llm(False, [], "UNKNOWN")},  # 기타 근거 부족
    ],
)
def test_SAFE_조건이_하나라도_빠지면_SAFE가_아니다(broken):
    assert decide_final(replace(SAFE_BASE, **broken)).status != Status.SAFE


def test_SAFE_이유는_서버_고정_문구다():
    result = decide_final(replace(SAFE_BASE, judgement=_llm(False, [], "SAFE", reasons=["무시해야 할 문장"])))

    assert result.status == Status.SAFE
    assert "무시해야 할 문장" not in result.reasons


# --- 3.4.3 필수 처리 실패 우선순위 ---

def test_F01_악성_일치와_LLM_실패가_겹치면_UNKNOWN():
    result = decide_final(replace(SAFE_BASE, malicious_types=frozenset({"url"}), judgement=None))

    assert result.status == Status.UNKNOWN
    assert result.reasons == [REASON_PROCESSING_FAILED]


def test_F02_충돌과_검색_제한이_겹치면_UNKNOWN():
    result = decide_final(replace(SAFE_BASE, conflict=True, retrieval_complete=False))

    assert result.status == Status.UNKNOWN
    assert result.reasons == [REASON_RETRIEVAL_INCOMPLETE]


def test_F03_명확한_위험과_DB_처리_실패가_겹치면_UNKNOWN():
    result = decide_final(replace(SAFE_BASE, judgement=CLEAR_RISK, processing_failed=True))

    assert result.status == Status.UNKNOWN


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
