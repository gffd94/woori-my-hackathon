"""잘못된 호스트가 정상 도메인으로 변환되는 문제를 막는 회귀 테스트."""

import pytest

from app.services.extractor import extract_entities, normalize_domain, normalize_url


@pytest.mark.parametrize('host', ['notice.example..', 'notice..example', r'notice.example\other', 'notice%2eexample'])
def test_invalid_host_is_rejected(host):
    with pytest.raises(ValueError):
        normalize_domain(host)


def test_malformed_host_is_not_normalized_into_official_domain():
    result = extract_entities('https://notice.example../check')
    assert result.domains == []
    assert result.unparsed_urls == ['https://notice.example../check']


def test_normalize_url_does_not_silently_remove_control_characters():
    with pytest.raises(ValueError):
        normalize_url('https://not\tice.example/check')


def test_single_dns_root_dot_remains_supported():
    assert normalize_domain('NOTICE.example.') == 'notice.example'
    assert normalize_url('https://NOTICE.example./check') == 'https://notice.example/check'
