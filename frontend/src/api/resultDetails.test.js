import test from 'node:test';
import assert from 'node:assert/strict';
import { withResultDetails, safeSourceHref, compactReason, compactReasons } from './resultDetails.js';

test('실제 API의 문자열 이유에 설명을 붙이고 링크를 별도로 표시한다', () => {
  const result = withResultDetails({ status: 'RISK', reasons: ['비공식 URL 신호가 확인되었습니다'] },
    '확인 https://suspect.example/check?token=secret#private https://other.example');
  assert.ok(result.reasons[0].detail);
  assert.deepEqual(result.messageLinks, ['https://suspect.example/check', 'https://other.example/']);
  assert.equal(result.reasons[0].title, '비공식 URL 신호가 확인되었습니다');
});

test('샘플의 설명은 유지하며 링크를 악성 일치로 단정하지 않는다', () => {
  const reason = { code: 'url', title: '출처 불명 URL', detail: '기존 설명' };
  const result = withResultDetails({ status: 'RISK', reasons: [reason] },
    'https://user:password@suspect.example/a https://user:password@suspect.example/a');
  assert.deepEqual(result.reasons, [reason]);
  assert.deepEqual(result.messageLinks, ['https://suspect.example/a']);
});

test('모르는 이유와 링크 없는 문자를 추측으로 채우지 않는다', () => {
  const result = withResultDetails({ status: 'UNKNOWN', reasons: ['새로운 이유'] }, '일반 문자');
  assert.deepEqual(result.reasons, [{ title: '새로운 이유' }]);
  assert.deepEqual(result.messageLinks, []);
});

test('긴 경로 토큰은 가리고 안전 판정에는 링크 확인 목록을 붙이지 않는다', () => {
  const text = 'www.suspect.example/abc1234567890123456789';
  assert.deepEqual(withResultDetails({ status: 'RISK' }, text).messageLinks,
    ['https://www.suspect.example/[가림]']);
  assert.deepEqual(withResultDetails({ status: 'SAFE' }, text).messageLinks, []);
});

test('서버 근거와 출처를 유지하며 기존 API에는 빈 근거 목록을 제공한다', () => {
  const evidence = [{ kind: 'pattern', title: '유사 수법', sources: [{ title: '참고 자료' }] }];
  assert.deepEqual(withResultDetails({ evidence }).evidence, evidence);
  assert.deepEqual(withResultDetails({}).evidence, []);
});

test('참고 자료만 HTTPS로 열며 위험한 주소 형식은 거부한다', () => {
  for (const url of ['javascript:alert(1)', 'http://ref.example', 'https://user:pass@ref.example', 'https://localhost', null]) {
    assert.equal(safeSourceHref(url), null);
  }
  assert.equal(safeSourceHref('https://reference.example/post?id=1'), 'https://reference.example/post?id=1');
});
test('화면용 위험 신호는 짧은 제목과 설명으로 표시한다', () => {
  assert.deepEqual(compactReason({ title: '지인·가족 사칭 신호가 확인되었습니다' }),
    { title: '지인·가족 사칭', detail: '지인이나 가족을 내세운 요청' });
  assert.deepEqual(compactReason({ title: '개인 번호로 연락 유도 신호가 확인되었습니다' }),
    { title: '개인 번호 연락 유도', detail: '문자 속 연락처로 응답 유도' });
});
test('다른 원문이 같은 화면 문구로 요약되면 한 번만 표시한다', () => {
  const reasons = [
    { title: '기관 사칭 신호가 확인되었습니다' },
    { title: '비공식 URL 신호가 확인되었습니다' },
    { title: '확인되지 않은 URL·전화번호가 있어 추가 확인이 필요합니다' },
    { title: '송금·결제 요구 신호가 확인되었습니다' },
    { title: '금전·상품권 요청 신호가 확인되었습니다' },
    { title: '인증 요구 신호가 확인되었습니다' },
  ];
  assert.deepEqual(compactReasons(reasons).map(r => r.title),
    ['기관 사칭 가능성', '미확인 링크·연락처', '금전 요구', '인증 요구']);
  assert.equal(reasons.length, 6);
});

test('제목이 같아도 설명이 다른 근거는 유지한다', () => {
  const reasons = [{ title: '추가 신호', detail: '첫 근거' }, { title: '추가 신호', detail: '다른 근거' }];
  assert.deepEqual(compactReasons(reasons), reasons);
});
