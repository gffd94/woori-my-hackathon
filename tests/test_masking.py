"""개인정보 최소화 (SPEC 1.6, 3.7.1 S-01·S-02). 합성 값만 쓴다."""

import pytest

from app.services.masking import mask_text, mask_url


@pytest.mark.parametrize(
    "raw, hidden, marker",
    [
        ("문의 010-1234-5678 로 연락", "1234-5678", "[전화번호]"),
        ("문의01012345678입니다", "01012345678", "[전화번호]"),
        ("주민번호 900101-1234567 확인", "1234567", "[주민등록번호]"),
        ("카드 1234-5678-9012-3456 결제", "9012-3456", "[카드번호]"),
        ("계좌 110-123-456789 입금", "456789", "[번호]"),
        # 13자리 연속 숫자는 주민등록번호 형태와 겹쳐 [주민등록번호]로 가려지므로 14자리로 확인한다
        ("계좌 12345678901234 입금", "12345678901234", "[번호]"),
        ("메일 tester@mail.example 로", "tester@mail.example", "[이메일]"),
    ],
)
def test_개인정보_형태를_가린다(raw, hidden, marker):
    masked = mask_text(raw)

    assert hidden not in masked
    assert marker in masked


def test_URL의_쿼리와_fragment는_가리고_호스트와_경로는_남긴다():
    masked = mask_url("https://malicious.example/login?token=secret-token-value&id=900101#frag")

    assert masked.startswith("https://malicious.example/login")
    assert "secret-token-value" not in masked
    assert "frag" not in masked


def test_URL의_사용자정보는_지운다():
    assert "demo:pass" not in mask_url("https://demo:pass@official.example/a")


def test_URL_경로의_긴_토큰은_가린다():
    masked = mask_url("https://unknown.example/r/AbCdEfGhIjKlMnOpQrSt12345")

    assert "AbCdEfGhIjKlMnOpQrSt12345" not in masked
    assert masked.startswith("https://unknown.example/r/")


def test_문장_속_URL과_개인정보를_함께_처리한다():
    message = "가상은행 010-0000-1111 https://malicious.example/a?session=abc123 본인인증"

    masked = mask_text(message)

    assert "010-0000-1111" not in masked
    assert "session=abc123" not in masked
    assert "https://malicious.example/a" in masked
    assert "가상은행" in masked and "본인인증" in masked


def test_URL_경로의_숫자는_전화번호로_가리지_않고_URL_규칙으로만_처리한다():
    masked = mask_text("https://notice.example/01012345678")

    assert "[전화번호]" not in masked


def test_해석할_수_없는_URL은_통째로_가린다():
    assert mask_url("https://bad.example:wrong/x") == "[URL]"


def test_개인정보가_없으면_그대로_둔다():
    assert mask_text("택배 주소 불일치 안내") == "택배 주소 불일치 안내"
