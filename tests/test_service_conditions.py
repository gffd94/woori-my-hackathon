"""추출·조회 경계 조건. 실제 인물·기관·연락처 대신 가상 데이터를 쓴다."""

import pytest

from app.services.extractor import extract
from app.services.retriever import search_similar_cases


def test_phone_adjacent_to_korean_text():
    assert extract('문의010-0000-0000입니다').phones == ['01000000000']


def test_phone_inside_identifier_is_not_contact():
    assert extract('code01000000000suffix').phones == []


def test_balanced_url_parentheses_are_preserved():
    assert extract('(https://notice.example/Help(FAQ)).').urls == ['https://notice.example/Help(FAQ)']


def test_userinfo_is_not_mistaken_for_official_host():
    assert extract('https://bank.example@evil.test/check').domains == ['evil.test']


def test_invalid_port_is_ignored_without_crashing():
    assert extract('https://notice.example:wrong/check').urls == []


def test_organization_list_is_explicit_and_deduplicated():
    result = extract('가상은행 안내', ['가상은행', '가상은행', '', '가상카드'])
    assert result.organizations == ['가상은행']
    assert extract('가상은행 안내').organizations == []


@pytest.mark.parametrize('limit', [True, 1.5, '3', None])
def test_limit_requires_integer(limit):
    with pytest.raises(ValueError):
        search_similar_cases(None, [0.1] * 1536, limit=limit)


@pytest.mark.parametrize('value', [True, '0.1', None, 10 ** 1000])
def test_vector_requires_finite_numbers(value):
    with pytest.raises(ValueError):
        search_similar_cases(None, [value] * 1536)
