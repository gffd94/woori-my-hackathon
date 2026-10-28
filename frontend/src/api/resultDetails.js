// 서버 판정은 그대로 두고, 고정된 이유의 의미만 풀어 설명합니다.
const DETAILS = [
  [/신고된 악성 (URL|도메인)/, '서버에 등록된 악성 링크 정보와 일치하는 요소가 발견됐어요. 문자 속 링크를 누르지 마세요.'],
  [/신고된 악성 전화번호/, '서버에 등록된 악성 전화번호와 일치하는 번호가 발견됐어요. 해당 번호로 연락하지 마세요.'],
  [/확인되지 않은 URL|비공식 URL/, '공식 정보로 확인되지 않은 링크나 연락처가 있어요. 공식 앱이나 대표번호로 따로 확인해 주세요.'],
  [/기관 사칭/, '기관을 내세워 접속·인증·연락 등을 요구하는 신호예요. 실제 발신 기관인지는 별도 확인이 필요해요.'],
  [/지인·가족 사칭|가족 사칭/, '지인이나 가족을 내세워 요청하는 신호예요. 원래 알고 있던 연락처로 직접 확인해 주세요.'],
  [/긴급성 압박/, '정지·마감 등으로 서두르게 하는 신호예요. 급하게 링크를 누르거나 요청에 응하지 마세요.'],
  [/인증 요구|개인정보 요구/, '인증번호나 개인정보 제공을 유도하는 신호예요. 문자 속 링크에서 정보를 입력하지 마세요.'],
  [/송금·결제|금전·상품권/, '돈이나 상품권을 보내도록 유도하는 신호예요. 보내기 전에 상대방을 직접 확인해 주세요.'],
  [/앱 설치/, '앱 설치를 유도하는 신호예요. 문자로 전달된 설치 파일을 실행하지 마세요.'],
  [/전화 연락 유도|개인 번호로 연락|답장·회신/, '문자에서 안내한 연락처로 응답하도록 유도하는 신호예요. 공식 대표번호로 따로 확인해 주세요.'],
];

function messageLinks(text) {
  const matches = text.match(/https?:\/\/[^\s<>"']+|www\.[^\s<>"']+|bit\.ly\/[^\s<>"']+/gi) || [];
  return [...new Set(matches.flatMap((raw) => {
    try {
      const url = new URL(/^https?:/i.test(raw) ? raw : `https://${raw}`);
      // 사용자정보·쿼리·fragment와 긴 토큰은 화면에 다시 노출하지 않습니다.
      const path = url.pathname.split('/').map((part) =>
        part.length >= 16 && /\d/.test(part) ? '[가림]' : part).join('/');
      return [`${url.protocol}//${url.host}${path}`];
    } catch { return []; }
  }))];
}

export function withResultDetails(result, text = '') {
  return {
    ...result,
    evidence: Array.isArray(result.evidence) ? result.evidence : [],
    reasons: (result.reasons || []).map((reason) => {
      const r = typeof reason === 'string' ? { title: reason } : reason;
      const detail = r.detail || DETAILS.find(([pattern]) => pattern.test(r.title))?.[1];
      return detail ? { ...r, detail } : r;
    }),
    // API는 링크별 판정을 주지 않으므로 악성 일치 목록으로 표시하지 않습니다.
    messageLinks: result.status === 'RISK' || result.status === 'CAUTION' ? messageLinks(text) : [],
  };
}

export function safeSourceHref(value) {
  if (typeof value !== 'string' || /[\s\u0000-\u001f]/u.test(value)) return null;
  try {
    const url = new URL(value);
    if (url.protocol !== 'https:' || url.username || url.password || !url.hostname.includes('.') ||
        url.port || /(?:\.local|\.localhost|\.internal)$/.test(url.hostname) ||
        /^[\d.]+$/.test(url.hostname) || url.hostname.includes(':') ||
        /token|password|secret|auth|email/i.test(url.search)) return null;
    return url.href;
  } catch { return null; }
}
