// 백엔드 없이 화면을 확인하기 위한 가짜 판정입니다. 실제 판정 로직이 아닙니다.
const wait = (ms) => new Promise((r) => setTimeout(r, ms));
const KNOWN_SCAM = ['parcel-check.example'];
const URL_RE = /(https?:\/\/\S+|www\.\S+|bit\.ly\/\S+)/i;

export async function mockAnalyze({ text }) {
  // 분석 중 말풍선 4단계(1.4초씩)가 한 바퀴 보이도록 시연용 대기
  await wait(5000);
  if (/\[오류\]/.test(text)) throw new Error('mock error');
  const url = (text.match(URL_RE) || [])[0];
  const r = [];

  if (url && KNOWN_SCAM.some((k) => url.includes(k))) {
    return {
      status: 'RISK', risk_level: 'high', basis: 'entities', matched_cases: 3, guide_type: 'damage_stage',
      reasons: [
        { code: 'url', title: '출처 불명 URL', detail: '공식 기관 도메인인지 확인되지 않음' },
        { code: 'urgency', title: '긴급 행동 유도', detail: '주소 확인을 위해 즉시 행동 요구' },
        { code: 'impersonation', title: '택배 사칭 가능성', detail: '익숙한 배송 문구로 클릭 유도' },
      ],
    };
  }
  if (url) r.push({ code: 'url', title: '출처 불명 URL', detail: '공식 기관 도메인인지 확인되지 않음' });
  if (/정지|만료|긴급|즉시|오늘까지/.test(text)) r.push({ code: 'urgency', title: '긴급 행동 유도', detail: '정지나 기한을 언급하며 서두르게 함' });
  if (/은행|카드|금융|택배|배송|검찰|경찰/.test(text) && url) r.push({ code: 'impersonation', title: '기관 사칭 가능성', detail: '익숙한 기관 이름으로 클릭 유도' });
  if (/인증|비밀번호|개인정보|본인확인/.test(text)) r.push({ code: 'other', title: '정보 입력 요구', detail: '인증이나 개인정보 입력을 요구함' });
  if (url && r.length >= 2) {
    return { status: 'RISK', risk_level: 'high', basis: 'llm', matched_cases: 0, guide_type: 'damage_stage', reasons: r };
  }
  if (/우리카드|우리은행/.test(text) && /앱에서/.test(text) && !url && !/송금|입금|010/.test(text)) {
    return {
      status: 'SAFE', risk_level: 'none', basis: 'entities', matched_cases: 0, guide_type: 'prevention',
      reasons: [
        { code: 'other', title: '공식 발신 번호', detail: '우리카드 대표번호와 일치' },
        { code: 'other', title: '정보 요구 없음', detail: '링크 클릭·정보 입력 요구 없음' },
        { code: 'other', title: '송금 요구 없음', detail: '돈을 보내라고 하지 않음' },
      ],
    };
  }
  // 주의 신호가 있지만 단정할 수 없는 경우 → CAUTION
  if (/지원금|환급|당첨|보상|010-|담당자/.test(text)) {
    const c = [];
    if (/지원금|환급|당첨|보상/.test(text)) c.push({ code: 'other', title: '지원금 안내', detail: '지급 조건을 공식 채널에서 확인' });
    if (/010-/.test(text)) c.push({ code: 'other', title: '개인 연락처', detail: '기관 대표번호인지 확인이 필요함' });
    c.push({ code: 'other', title: '기관명 생략', detail: '안내를 보낸 기관이 적혀 있지 않음' });
    return { status: 'CAUTION', risk_level: 'low', matched_cases: 0, guide_type: 'need_more_info', reasons: c };
  }
  // 판단 근거가 될 정보 자체가 부족한 경우 → NO_DATA
  return {
    status: 'NO_DATA', risk_level: 'none', matched_cases: 0, guide_type: 'need_more_info',
    reasons: [
      { code: 'other', title: '문자 전체', detail: '앞뒤 내용이 포함된 원문을 보내요' },
      { code: 'other', title: 'URL·이미지', detail: '주소나 선명한 캡처를 보내주세요' },
    ],
  };
}

export async function mockReport() {
  await wait(500);
  return { case_id: 1024, status: 'pending', report_count: 1 };
}

export const SAMPLES = {
  known: '[택배 배송 안내]\n고객님의 상품이 주소 불일치로 반송되었습니다.\n아래 링크에서 배송 정보를 확인해주세요.\nhttps://parcel-check.example/a8z',
  newRisk: '[우리은행] 고객님의 계좌가 정지될 예정입니다.\n아래 링크에서 본인인증을 진행해주세요.\nhttp://woori-secure.example/verify',
  safe: '[우리카드] 10월 이용대금 325,400원이\n11월 5일 결제될 예정입니다.\n자세한 내용은 우리카드 앱에서 확인해주세요.',
  caution: '[지원금 안내]\n고객님께 특별 지원금이 지급될 예정입니다.\n자세한 내용은 담당자에게 문의해주세요.\n010-XXXX-XXXX',
  noData: '[안내]\n자세한 내용은 확인 후 연락해주세요.',
};
