"""① 문자에서 URL·도메인·전화번호·기관명을 추출한다. 링크에 접속하지 않는다."""

import re
from dataclasses import dataclass, field
from urllib.parse import urlsplit, urlunsplit


URL_PATTERN = re.compile(r"(?:https?://|www\.)[^\s<>\"']+", re.IGNORECASE)
# 스킴 없이 적힌 주소(SPEC 2.6). 일반 문장의 마침표를 도메인으로 오인하지 않도록
# 허용한 최상위 도메인으로 끝나는 형태만 인정한다. example·test는 문서·테스트용 예약 도메인이다.
BARE_TLDS = (
    "com", "net", "org", "kr", "co", "me", "ly", "io", "xyz", "top", "shop", "site", "info", "biz",
    "cc", "link", "app", "dev", "ai", "online", "store", "club", "vip", "pw", "tk", "gl", "gd", "to",
    # 스미싱 단축·피싱 주소에 자주 쓰이는 최상위 도메인 (예: me2.do, tsu.im, s.id, ….guru)
    "do", "im", "id", "su", "ru", "cn", "guru", "buzz", "red", "fund", "tech", "space", "cloud", "pro",
    "click", "work", "live", "life", "fun", "icu", "cyou", "today", "mba", "monster",
    "example", "test",
)
BARE_URL_PATTERN = re.compile(
    r"(?<![A-Za-z0-9_@.\-/])"  # 이메일·다른 주소의 일부가 아니어야 한다. 한글과는 붙어 있어도 된다.
    r"(?:[a-z0-9](?:[a-z0-9\-]*[a-z0-9])?\.)+(?:" + "|".join(BARE_TLDS) + r")"
    r"(?![a-z0-9\-])(?:/[^\s<>\"']*)?",
    re.IGNORECASE,
)
PHONE_PATTERN = re.compile(
    r"(?<![A-Za-z0-9_])(?:01[016789][ -]?\d{3,4}[ -]?\d{4}"
    r"|0(?:2|[3-6]\d|70)[ -]?\d{3,4}[ -]?\d{4}"
    r"|1[568]\d{2}[ -]?\d{4})(?![A-Za-z0-9_])"
)


@dataclass
class ExtractedEntities:
    urls: list[str] = field(default_factory=list)
    domains: list[str] = field(default_factory=list)
    phones: list[str] = field(default_factory=list)
    organizations: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    unparsed_urls: list[str] = field(default_factory=list)
    has_userinfo: bool = False


def normalize_domain(value: str) -> str:
    """DB 적재·조회 공통 호스트 규칙. 하위 도메인은 합치지 않는다."""
    # DNS 루트 점 하나만 허용한다. 여러 점을 지워 다른 주소와 합치지 않는다.
    host = value.lower().removesuffix('.')
    if (
        not host
        or any(char.isspace() or ord(char) < 32 or ord(char) == 127 for char in host)
        or any(char in host for char in '\\/%@?#[]')
        or any(not label for label in host.split('.'))
    ):
        raise ValueError('유효하지 않은 호스트입니다')
    return host if ':' in host else host.encode('idna').decode('ascii')


def normalize_url(value: str) -> str:
    """사용자 정보를 제거하고 기본 포트·루트 슬래시를 통일한다.

    DB URL 적재에도 이 함수를 사용한다. www.는 https://로 해석한다.
    http와 https, www와 다른 호스트는 서로 합치지 않는다.
    경로·쿼리·fragment는 보존한다. 이 함수의 반환값만으로 신뢰성을 판단하지 않는다.
    사용자 정보가 있는 URL은 extract_entities에서 별도 추가 확인 대상으로 표시한다.
    """
    # urlsplit이 탭·개행 등을 지우기 전에 검사해 원문과 다른 주소가 되지 않게 한다.
    if any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise ValueError('URL에 제어 문자가 포함되어 있습니다')
    candidate = 'https://' + value if value.lower().startswith('www.') else value
    parts = urlsplit(candidate)
    if parts.scheme.lower() not in ('http', 'https') or not parts.hostname:
        raise ValueError('HTTP(S) 호스트가 필요합니다')
    host = normalize_domain(parts.hostname)
    port = parts.port
    authority = f'[{host}]' if ':' in host else host
    if port is not None and (parts.scheme.lower(), port) not in (('http', 80), ('https', 443)):
        authority += f':{port}'
    path = '' if parts.path == '/' else parts.path
    return urlunsplit((parts.scheme.lower(), authority, path, parts.query, parts.fragment))


def normalize_phone(value: str) -> str:
    """DB 적재 시에도 같은 규칙으로 전화번호의 구분자를 제거한다."""
    return re.sub(r"\D", "", value)


def _trim_url(raw: str) -> str:
    # 쿼리가 있으면 끝 구두점도 값일 수 있으므로 임의로 지우지 않는다.
    punctuation = '.,!?;:，。' if '?' not in raw and '#' not in raw else ''
    raw = raw.rstrip(punctuation) if punctuation else raw
    # 문장을 감싼 괄호만 제거하고 URL 내부의 짝이 맞는 괄호는 보존한다.
    while raw and raw[-1] in ')]}':
        closing = raw[-1]
        opening = {')': '(', ']': '[', '}': '{'}[closing]
        if raw.count(closing) <= raw.count(opening):
            break
        raw = raw[:-1]
        if punctuation:
            raw = raw.rstrip(punctuation)
    return raw


def extract_entities(message: str, organization_names: list[str] | None = None) -> ExtractedEntities:
    """기관명은 팀에서 관리하는 목록을 전달받아 단순 문자열로 추출한다.

    URL은 http(s)://, www.로 시작하는 주소와 허용한 최상위 도메인으로 끝나는 스킴 없는 주소를 지원한다.
    도메인만 소문자로 통일하고 경로·쿼리의 대소문자는 보존한다.
    unparsed_urls에는 파싱 실패 또는 일반 DB 비교를 보류할 URL이 들어간다.
    URL 원문에 개인정보가 있을 수 있으므로 결과를 그대로 로그·화면에 출력하지 않는다.
    """
    result = ExtractedEntities()
    # 스킴 있는 주소를 먼저 지운 뒤 스킴 없는 주소를 찾아, 같은 주소를 두 번 읽지 않는다.
    without_schemed = URL_PATTERN.sub(' ', message)
    raws = [_trim_url(m.group()) for m in URL_PATTERN.finditer(message)]
    raws += [_trim_url(m.group()) for m in BARE_URL_PATTERN.finditer(without_schemed)]
    for raw in raws:
        # www.와 스킴 없는 주소는 https://로 해석한다. 확인이 필요한 목록에는 원문을 남긴다.
        candidate = raw if raw.lower().startswith(('http://', 'https://')) else 'https://' + raw
        try:
            has_userinfo = '@' in urlsplit(candidate).netloc
            url = normalize_url(candidate)
            host = urlsplit(url).hostname
        except (ValueError, UnicodeError):
            result.unparsed_urls.append(raw)
            result.warnings.append('URL을 해석하지 못해 추가 확인이 필요합니다')
            continue
        if has_userinfo:
            result.has_userinfo = True
            # 정규화로 사용자 정보가 사라진 주소를 공식 URL과 곧바로 매칭하지 않는다.
            # 기존 retriever는 이 목록이 있으면 예외를 발생시켜 UNKNOWN으로 연결한다.
            result.unparsed_urls.append(raw)
            result.warnings.append('사용자 정보가 포함된 URL은 추가 확인이 필요합니다')
        result.urls.append(url)
        result.domains.append(host)

    # URL 경로 안의 숫자를 전화번호로 잘못 뽑지 않는다.
    without_urls = BARE_URL_PATTERN.sub(' ', without_schemed)
    result.phones = [normalize_phone(m.group()) for m in PHONE_PATTERN.finditer(without_urls)]
    result.organizations = [name for name in (organization_names or []) if name and name in message]
    result.urls = list(dict.fromkeys(result.urls))
    result.domains = list(dict.fromkeys(result.domains))
    result.phones = list(dict.fromkeys(result.phones))
    result.organizations = list(dict.fromkeys(result.organizations))
    result.warnings = list(dict.fromkeys(result.warnings))
    result.unparsed_urls = list(dict.fromkeys(result.unparsed_urls))
    return result


def extract(message: str, organization_names: list[str] | None = None) -> ExtractedEntities:
    """기존 호출자 호환용. 신규 코드에서는 extract_entities를 사용한다."""
    return extract_entities(message, organization_names)
