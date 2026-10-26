from app.services.extractor import extract, normalize_phone


def test_extract_links_phones_and_organizations():
    result = extract(
        '가상은행 안내 https://Notice.example/check). 문의 02-123-4567 또는 1588-0000',
        organization_names=['가상은행'],
    )
    assert result.urls == ['https://notice.example/check']
    assert result.domains == ['notice.example']
    assert result.phones == ['021234567', '15880000']
    assert result.organizations == ['가상은행']


def test_duplicates_and_www():
    result = extract('www.notice.example 안내 www.notice.example 010-0000-0000 01000000000')
    assert result.urls == ['https://www.notice.example']
    assert result.phones == ['01000000000']


def test_url_path_keeps_case_and_phone_in_url_is_not_extracted():
    result = extract('https://NOTICE.example/Check/01000000000?token=AbC')
    assert result.urls == ['https://notice.example/Check/01000000000?token=AbC']
    assert result.phones == []


def test_empty_and_long_numbers():
    assert extract('').urls == []
    assert extract('1234010000000005678').phones == []
    assert normalize_phone('010-0000-0000') == '01000000000'


def test_disguised_domain_is_preserved():
    assert extract('https://bank.example.evil.test').domains == ['bank.example.evil.test']
