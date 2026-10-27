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


def test_U38_스킴_없는_도메인도_추출한다():
    result = extract('자세한 내용은 official.example에서 확인하세요')
    assert result.urls == ['https://official.example']
    assert result.domains == ['official.example']


def test_스킴_없는_주소의_경로를_보존하고_경로의_숫자는_전화번호가_아니다():
    result = extract('bit.ly/Ab01000000000 클릭')
    assert result.urls == ['https://bit.ly/Ab01000000000']
    assert result.domains == ['bit.ly']
    assert result.phones == []


def test_스킴_없는_국내_도메인():
    assert extract('notice.co.kr 참고').domains == ['notice.co.kr']


def test_이메일_마침표_숫자는_도메인으로_뽑지_않는다():
    result = extract('help@bank.example 로 문의. 확인했습니다.감사합니다 버전 3.14')
    assert result.urls == []
    assert result.domains == []


def test_스킴_있는_주소와_같은_주소는_한_번만_뽑는다():
    result = extract('https://notice.example 또는 notice.example')
    assert result.urls == ['https://notice.example']
    assert result.domains == ['notice.example']


def test_U38_스킴_없는_도메인도_추출한다():
    result = extract('자세한 내용은 official.example에서 확인하세요')
    assert result.urls == ['https://official.example']
    assert result.domains == ['official.example']


def test_스킴_없는_주소의_경로를_보존하고_경로의_숫자는_전화번호가_아니다():
    result = extract('bit.ly/Ab01000000000 클릭')
    assert result.urls == ['https://bit.ly/Ab01000000000']
    assert result.domains == ['bit.ly']
    assert result.phones == []


def test_스킴_없는_국내_도메인():
    assert extract('notice.co.kr 참고').domains == ['notice.co.kr']


def test_이메일_마침표_숫자는_도메인으로_뽑지_않는다():
    result = extract('help@bank.example 로 문의. 확인했습니다.감사합니다 버전 3.14')
    assert result.urls == []
    assert result.domains == []


def test_스킴_있는_주소와_같은_주소는_한_번만_뽑는다():
    result = extract('https://notice.example 또는 notice.example')
    assert result.urls == ['https://notice.example']
    assert result.domains == ['notice.example']
