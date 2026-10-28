"""근거·출처 전달: 실제 DB와 외부 API를 차단한 합성 데이터 검증."""
from dataclasses import replace

import pytest

from app.schemas.analyze import ReferenceSource
from app.services.analyzer import PatternCard, SearchOutcome
from app.services.llm_judge import LLMJudgement, Signal
from tests.analyze_support import Fakes, block_real_calls, malicious
from tests.test_repository import FakeSession, Result
from app.services.repository import search_cards
from app.services.retriever import PatternMatch, PatternRetrieval


@pytest.fixture(autouse=True)
def _block(block_real_calls):
    yield
    assert block_real_calls == []


def test_악성_일치와_연결된_참고자료를_구분하고_민감정보를_가린다():
    source = ReferenceSource(title='가상 택배 수법', site='가상 자료실', url='https://reference.example/post/1')
    card = PatternCard(id=7, name='가상 배송 사칭', sources=(source, source))
    f = Fakes(lookup_result=malicious(('domain', 'bad.example')),
              outcome=SearchOutcome('completed', 'hybrid', 'complete', (card,)))
    result = f.analyzer().analyze('https://bad.example/check?token=secret')
    match = next(e for e in result.evidence if e.kind == 'indicator_match')
    assert 'bad.example' in match.value and 'secret' not in match.value
    assert match.sources == []
    pattern = next(e for e in result.evidence if e.kind == 'pattern')
    assert pattern.sources == [source]


def test_AI_근거는_입력에_존재할_때만_표시하고_UNKNOWN에는_숨긴다():
    f = Fakes(judgement=LLMJudgement(suspicious=True, signals=[
        Signal(signal='인증 요구', evidence='본인인증'),
        Signal(signal='기관 사칭', evidence='문자에 없는 문구'),
    ]))
    result = f.analyzer().analyze('본인인증을 하세요 https://new.example')
    assert [e.value for e in result.evidence if e.kind == 'signal'] == ['본인인증']
    f.fail.add('search')
    result = f.analyzer().analyze('본인인증을 하세요 https://new.example')
    assert not any(e.kind in ('signal', 'pattern') for e in result.evidence)


def test_출처_URL은_HTTPS만_허용하고_잘못된_주소는_링크로_보내지_않는다():
    for url in ['javascript:alert(1)', 'http://ref.example', 'https://user:pass@ref.example', 'https://localhost/a']:
        assert ReferenceSource(title='자료', url=url).url is None
    assert ReferenceSource(title='자료', url='https://reference.example/post?id=7').url.endswith('?id=7')


def test_공식정보_확인출처를_반환한다():
    f = Fakes()
    f.lookup_result = replace(f.lookup_result, official_domains=frozenset({'official.example'}),
        official_sources={'official.example': ReferenceSource(title='가상은행 확인 자료', url='https://reference.example/official')})
    result = f.analyzer().analyze('https://official.example/notice')
    evidence = next(e for e in result.evidence if e.kind == 'official_match')
    assert evidence.sources[0].url == 'https://reference.example/official'


def test_검색된_카드에_연결된_출처만_조회하고_중복을_제거한다(monkeypatch):
    class SourceSession(FakeSession):
        def execute(self, query, params=None):
            self.calls.append((str(query), params))
            row = dict(pattern_id=7, id=9, title='가상 자료', site='가상 자료실',
                       url='https://reference.example/post/9', posted_date=None)
            return Result([row, row, {**row, 'pattern_id': 999}])

    session = SourceSession()
    monkeypatch.setattr('app.services.repository.search_patterns', lambda *a: PatternRetrieval(
        'completed', 'hybrid', 'complete', patterns=[PatternMatch(7, '가상 수법', '요약', [], 0.1)]))
    result = search_cards('가상 문자', [0.1] * 1536, session_factory=lambda: session)
    assert len(result.patterns[0].sources) == 1
    assert session.calls[0][1] == {'ids': [7]}
    assert 'JOIN sources' in session.calls[0][0]
    assert session.rolled_back and not session.committed


def test_검색_완료후_LLM_실패에도_참고_자료는_남긴다():
    card = PatternCard(id=7, name='가상 수법')
    f = Fakes(outcome=SearchOutcome('completed', 'hybrid', 'complete', (card,)), fail={'judge'})
    result = f.analyzer().analyze('가상 문자')
    assert result.status.value == 'UNKNOWN'
    assert [(e.kind, e.sources) for e in result.evidence] == [('pattern', [])]


def test_출처_조회_실패는_성공한_검색으로_위장하지_않는다(monkeypatch):
    monkeypatch.setattr('app.services.repository.search_patterns', lambda *a: PatternRetrieval(
        'completed', 'hybrid', 'complete', patterns=[PatternMatch(7, '가상 수법', '요약', [], 0.1)]))
    f = Fakes()
    analyzer = f.analyzer()
    analyzer._search = lambda text, vector: search_cards(text, vector, session_factory=lambda: FakeSession(fail=True))
    result = analyzer.analyze('가상 문자')
    assert result.status.value == 'UNKNOWN'
    assert result.retrieval.status == 'failed'
    assert result.matched_cases is None
    assert not any(e.kind == 'pattern' for e in result.evidence)


def test_공식정보_출처를_DB_대조에서_전달한다():
    from app.services.extractor import extract_entities
    from app.services.repository import lookup_indicators

    class OfficialSession(FakeSession):
        def execute(self, query, params=None):
            if 'FROM official_links' in str(query):
                return Result([dict(domain='official.example', organization='가상은행',
                                    verification_reference='https://reference.example/official')])
            return super().execute(query, params)

    result = lookup_indicators(extract_entities('https://official.example/notice'), session_factory=OfficialSession)
    assert result.official_sources['official.example'].url == 'https://reference.example/official'


def test_메타데이터와_일치한_전화번호는_마스킹한다():
    source = ReferenceSource(title='가상 자료 900101-1234567', site='010-0000-1111')
    assert '900101-1234567' not in source.title
    assert '010-0000-1111' not in source.site
    result = Fakes(lookup_result=malicious(('phone', '01000001111'))).analyzer().analyze('연락 010-0000-1111')
    assert '01000001111' not in result.model_dump_json()
    assert next(e for e in result.evidence if e.kind == 'indicator_match').value == '[전화번호 1]'


def test_API_경로에서_출처를_포함한_근거를_직렬화한다():
    from fastapi.testclient import TestClient
    from app.main import app
    from app.routers.analyze import get_analyzer
    card = PatternCard(id=7, name='가상 수법', sources=(ReferenceSource(
        title='가상 자료', site='가상 자료실', url='https://reference.example/post/7'),))
    f = Fakes(outcome=SearchOutcome('completed', 'hybrid', 'complete', (card,)))
    app.dependency_overrides[get_analyzer] = lambda: f.analyzer()
    try:
        with TestClient(app) as client:
            response = client.post('/analyze', json={'message': '가상 문자'})
        assert response.status_code == 200
        assert response.json()['evidence'][0]['sources'][0]['url'] == 'https://reference.example/post/7'
    finally:
        app.dependency_overrides.clear()
