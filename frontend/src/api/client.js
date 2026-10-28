// 설계서 API 명세(POST /analyze, POST /reports)를 호출합니다.
// VITE_API_BASE_URL이 비어 있으면 mock.js의 가짜 응답을 씁니다.
import { mockAnalyze, mockReport } from './mock.js';
import { withResultDetails } from './resultDetails.js';

const BASE = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '');
const TIMEOUT_MS = 15000;

async function post(path, body) {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), TIMEOUT_MS);
  try {
    const res = await fetch(`${BASE}${path}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      signal: ctrl.signal,
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return await res.json();
  } finally {
    clearTimeout(timer);
  }
}

/**
 * @param {{text: string, source: 'share' | 'paste'}} req
 * @returns {Promise<AnalyzeResult>}
 *
 * AnalyzeResult = {
 *   status: 'RISK' | 'SAFE' | 'CAUTION' | 'NO_DATA',   // 예전 UNKNOWN은 NO_DATA로 처리
 *   risk_level: 'high' | 'medium' | 'low' | 'none',
 *   reasons: Array<string | {code?: 'url'|'urgency'|'impersonation'|'other', title: string, detail?: string}>,
 *   matched_cases: number,
 *   basis?: 'entities' | 'safe_browsing' | 'llm',
 *   guide_type: 'damage_stage' | 'prevention' | 'need_more_info'
 * }
 * 오류가 나면 화면에서는 일시 오류 안내로 처리합니다.
 */
export async function analyze(req) {
  if (!BASE) return withResultDetails(await mockAnalyze(req), req.text);
  // 백엔드 계약(SPEC 2.11)은 message 필드만 받고, 모르는 필드는 422로 거절합니다.
  return withResultDetails(normalize(await post('/analyze', { message: req.text, source: req.source })), req.text);
}

/** @param {{text: string, source: 'share' | 'paste', comment?: string}} req */
export async function report(req) {
  if (!BASE) return mockReport(req);
  // 백엔드에 POST /reports가 없습니다(MVP 제외). reportSupported로 화면에서 먼저 막습니다.
  throw new Error('report not supported');
}

function normalize(r) {
  return {
    ...r,
    // 백엔드는 낮은 위험을 RISK + risk_level low로 보냅니다. 화면에서는 CAUTION으로 보여 줍니다.
    status: r.status === 'RISK' && r.risk_level === 'low' ? 'CAUTION' : r.status,
    reasons: (r.reasons || []).map((x) => (typeof x === 'string' ? { code: 'other', title: x } : x)),
  };
}

export const usingMock = !BASE;
export const reportSupported = !BASE;
