"""외부 전달·판정 기록 전에 개인정보와 URL 민감 부분을 가린다 (SPEC 1.6).

명시한 형태만 가리며 모든 개인정보 탐지를 보장하지 않는다 (예: 이름·주소는 대상 아님).
"""

import re
from urllib.parse import urlsplit

from app.services.extractor import PHONE_PATTERN, URL_PATTERN

EMAIL_PATTERN = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
RRN_PATTERN = re.compile(r"(?<!\d)\d{6}[- ]?[1-8]\d{6}(?!\d)")
CARD_PATTERN = re.compile(r"(?<!\d)\d{4}[- ]\d{4}[- ]\d{4}[- ]\d{4}(?!\d)")
ACCOUNT_PATTERN = re.compile(r"(?<!\d)(?:\d{2,6}-\d{2,6}-\d{2,8}|\d{10,})(?!\d)")
# 단축 URL 코드보다 긴 경로 조각은 인증 토큰일 수 있다
TOKEN_SEGMENT = re.compile(r"^(?=.*\d)[A-Za-z0-9_\-=.~]{16,}$")

# 순서가 중요하다: 더 구체적인 형태를 먼저 가려야 일반 번호 규칙에 먹히지 않는다
TEXT_RULES = (
    (EMAIL_PATTERN, "[이메일]"),
    (RRN_PATTERN, "[주민등록번호]"),
    (CARD_PATTERN, "[카드번호]"),
    (PHONE_PATTERN, "[전화번호]"),
    (ACCOUNT_PATTERN, "[번호]"),
)


def mask_url(url: str) -> str:
    """호스트와 경로는 판단 근거로 남기고 사용자정보·쿼리·fragment·긴 토큰은 가린다."""
    candidate = "https://" + url if url.lower().startswith("www.") else url
    try:
        parts = urlsplit(candidate)
        host = parts.hostname
        port = parts.port
    except ValueError:
        return "[URL]"
    if not host or any(ord(char) < 32 for char in candidate):
        return "[URL]"

    authority = host if port is None else f"{host}:{port}"
    path = "/".join("[토큰]" if TOKEN_SEGMENT.match(seg) else seg for seg in parts.path.split("/"))
    masked = f"{parts.scheme.lower()}://{authority}{path}"
    if parts.query or parts.fragment:
        masked += "?[생략]"
    return masked


def _mask_plain(text: str) -> str:
    for pattern, marker in TEXT_RULES:
        text = pattern.sub(marker, text)
    return text


def mask_text(text: str) -> str:
    """URL은 URL 규칙으로, 나머지 문장은 개인정보 규칙으로 가린다."""
    pieces = []
    last = 0
    for match in URL_PATTERN.finditer(text):
        pieces.append(_mask_plain(text[last:match.start()]))
        pieces.append(mask_url(match.group()))
        last = match.end()
    pieces.append(_mask_plain(text[last:]))
    return "".join(pieces)
