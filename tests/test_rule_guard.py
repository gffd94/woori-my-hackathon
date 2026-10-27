"""규칙 기반 안전장치(SPEC 2.10.3). 고정 표현 조합만 확인한다."""

import pytest

from app.services.rule_guard import match_rules


@pytest.mark.parametrize('message,expected', [
    ('엄마 나 폰 액정 깨져서 수리 맡겼어 이 번호로 문자 줘', ['가족 사칭']),
    ('아빠 나 휴대폰 고장나서 임시폰이야 톡 줘', ['가족 사칭']),
    ('가상지검입니다. 귀하 명의 계좌가 범죄에 연루되어 연락 바랍니다', ['기관 연락 유도']),
    ('[가상카드] 고객님 카드가 발급되어 배송 예정입니다. 본인 신청이 아닐 경우 고객센터로 연락 바랍니다',
     ['카드·결제 확인 유도']),
])
def test_고정_표현_조합이_모두_있으면_일치한다(message, expected):
    assert match_rules(message) == expected


@pytest.mark.parametrize('message', [
    '엄마 오늘 저녁 뭐 먹어?',
    '폰 액정 깨져서 수리 맡겼어',
    '[가상택배] 오늘 14~16시 배송 예정입니다.',
    '[가상카드] 결제가 완료되었습니다.',
    '가상경찰서 교통안전 캠페인 안내',
])
def test_조합_일부만_있으면_일치하지_않는다(message):
    assert match_rules(message) == []


def test_띄어쓰기와_전각_문자_차이를_무시한다():
    assert match_rules('엄마  나 폰 액 정 깨졌어 문자줘') == ['가족 사칭']
    assert match_rules('ＯＫ 엄마 폰 고장 연락 줘') == ['가족 사칭']
