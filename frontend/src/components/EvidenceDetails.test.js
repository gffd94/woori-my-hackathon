import test from 'node:test';
import assert from 'node:assert/strict';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { build } from 'esbuild';

// 프로젝트에 설치된 Vite 의존성으로 JSX를 번들링해 실제 React 출력을 검사합니다.
const bundle = await build({ entryPoints: ['src/components/EvidenceDetails.jsx'],
  bundle: true, write: false, format: 'esm', platform: 'node', jsx: 'automatic' });
const { EvidenceDetails } = await import(`data:text/javascript;base64,${Buffer.from(bundle.outputFiles[0].text).toString('base64')}`);

test('근거와 간단한 출처 링크를 렌더링하고 게시일은 생략한다', () => {
  const html = renderToStaticMarkup(React.createElement(EvidenceDetails, { evidence: [
    { kind: 'pattern', title: '가상 수법', detail: '유사 수법 참고 자료', sources: [
      { title: '가상 안내문', site: '가상 자료실', posted_date: '2026-10-28', url: 'https://reference.example/post/7' },
    ] },
  ] }));
  for (const value of ['가상 안내문', '가상 자료실', 'noopener noreferrer', 'https://reference.example/post/7']) {
    assert.ok(html.includes(value));
  }
  assert.ok(!html.includes('2026-10-28'));
  assert.ok(!html.includes('가상 수법'));
  assert.ok(!html.includes('판단 근거와 참고 출처'));
});

test('의심 링크를 클릭 가능하게 만들지 않고 출처 누락과 시연용을 표시한다', () => {
  const html = renderToStaticMarkup(React.createElement(EvidenceDetails, { isMock: true, evidence: [
    { kind: 'indicator_match', title: '악성 단서', value: 'https://suspect.example/<script>', detail: 'DB 일치', sources: [] },
    { kind: 'pattern', title: '참고', sources: [{ title: '자료', url: 'javascript:alert(1)' }] },
  ] }));
  assert.ok(html.includes('출처 : 자료'));
  assert.ok(!html.includes('suspect.example'));
  assert.ok(!html.includes('<a '));
});

test('이전 API처럼 근거 배열이 없어도 렌더링한다', () => {
  assert.equal(renderToStaticMarkup(React.createElement(EvidenceDetails)), '');
});

test('출처 코드를 보호나라로 바꾸고 한 줄 출처와 링크만 표시한다', () => {
  const html = renderToStaticMarkup(React.createElement(EvidenceDetails, { evidence: [
    { kind: 'pattern', title: '유사 수법', sources: [
      { title: '가상 안내 자료', site: 'boho_security_notice', url: 'https://reference.example/post/1' },
    ] },
  ] }));
  assert.ok(html.includes('출처 : 보호나라'));
  assert.ok(!html.includes('boho_security_notice'));
  assert.ok(!html.includes('evidence__source-title'));
  assert.match(html, /<a[^>]*href="https:\/\/reference.example\/post\/1"[^>]*>원문보기<\/a>/);
  assert.ok(!html.includes('>https://reference.example'));
});

test('여러 근거에 연결된 동일 출처는 한 번만 표시한다', () => {
  const source = { title: '가상 자료', site: 'boho_security_notice', url: 'https://reference.example/post/1' };
  const html = renderToStaticMarkup(React.createElement(EvidenceDetails, { evidence: [
    { sources: [source] }, { sources: [source] }, { sources: [] },
  ] }));
  assert.equal((html.match(/출처 : 보호나라/g) || []).length, 1);
  assert.equal(renderToStaticMarkup(React.createElement(EvidenceDetails, { evidence: [{ sources: [] }] })), '');
});
