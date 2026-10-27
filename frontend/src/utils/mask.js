// 개인정보 자동 마스킹. 판정 근거가 되는 URL과 문자 속 연락처는 남기고,
// 고객 본인의 정보(주민번호·카드번호·계좌번호·인증번호·이름)만 가립니다.
// 백엔드에서도 같은 규칙으로 한 번 더 가립니다(LLM 호출 전, DB 저장 전, 로그 기록 전).

const URL_RE = /(https?:\/\/\S+|www\.\S+|bit\.ly\/\S+)/gi;
const PHONE_RE = /^0\d{1,2}-\d{3,4}-\d{4}$/;
const NOT_NAMES = ['고객', '회원', '담당자', '사장', '선생', '여러분', '대표', '직원', '상담사'];

const RULES = [
  { type: '주민등록번호', re: /\b\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])[-\s][1-4]\d{6}\b/g, to: () => '******-*******' },
  { type: '카드번호', re: /\b(\d{4})[-\s]?(\d{4})[-\s]?(\d{4})[-\s]?(\d{4})\b/g, to: (m, a, b, c, d) => `****-****-****-${d}` },
  {
    type: '인증번호',
    re: /((?:인증|승인|확인)\s*번호|OTP)(\s*[:은는]?\s*)(\d{4,8})/gi,
    to: (m, label, sep, num) => `${label}${sep}${'*'.repeat(num.length)}`,
  },
  {
    type: '계좌번호',
    re: /\b\d{2,6}(?:-\d{2,6}){2,3}\b/g,
    to: (m) => (PHONE_RE.test(m) ? m : m.replace(/\d/g, '*')),
    keepIf: (m) => PHONE_RE.test(m),
  },
  { type: '계좌번호', re: /\b(?!01)\d{10,14}\b/g, to: (m) => '*'.repeat(m.length) },
  {
    type: '이름',
    re: /([가-힣]{2,4})(\s?)(고객님|님)/g,
    to: (m, name, sp, suffix) => (NOT_NAMES.includes(name) ? m : `○○○${sp}${suffix}`),
    keepIf: (m, name) => NOT_NAMES.includes(name),
  },
];

/** @returns {{ text: string, count: number, types: string[] }} */
export function maskPersonalInfo(input) {
  let count = 0;
  const types = new Set();
  const parts = input.split(URL_RE);
  const out = parts.map((part) => {
    if (URL_RE.test(part)) { URL_RE.lastIndex = 0; return part; }
    URL_RE.lastIndex = 0;
    let s = part;
    for (const r of RULES) {
      s = s.replace(r.re, (...args) => {
        const m = args[0];
        if (r.keepIf && r.keepIf(...args)) return m;
        count += 1;
        types.add(r.type);
        return r.to(...args);
      });
    }
    return s;
  });
  return { text: out.join(''), count, types: [...types] };
}
