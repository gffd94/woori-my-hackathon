// 설계서 '챗봇 대화 플로우' 섹션을 그대로 옮긴 대화 노드입니다.
// 버튼 종류: go(다음 노드) · action(앱 이동/전화/외부 링크/안내) · sample(예시 문자 분석)
//   action.kind: 'app'  → 우리WON뱅킹 기존 화면으로 이동 (target = 앱 라우트)
//                'tel'  → 전화 연결 (target = 번호)
//                'link' → 외부 링크 (target = URL)
//                'info' → 안내 토스트

import { reportSupported } from '../api/client.js';

const END = [
  { label: '다른 문자 확인', go: 'paste' },
  { label: '처음으로', go: 'restart' },
];
const REPORT = { label: '신고하기', go: 'report' };
const tel = (n, label) => ({ label, action: { kind: 'tel', target: n, toast: `${n}로 전화를 연결해요.` } });
const CS = { label: '고객센터 연결', action: { kind: 'tel', target: 'WOORI_CS', toast: '우리은행 고객센터로 전화를 연결해요.' } };
const CALL112 = tel('112', '112 전화 연결');
const CALL118 = tel('118', '118 상담 연결');

export const INPUT_INFO = [
  { key: 'pw', label: '계좌·카드 비밀번호', desc: '바로 비밀번호를 바꾸세요.', button: { label: '비밀번호 변경하기', action: { kind: 'app', target: 'password-change', toast: '비밀번호 변경 화면으로 이동해요.' } } },
  { key: 'otp', label: '인증번호', desc: '인증번호로 대출이나 이체가 실행될 수 있어 바로 확인이 필요해요.', button: CS },
  { key: 'card', label: '카드번호', desc: '카드를 정지하고 재발급 받으세요.', button: { label: '카드 분실·정지 신고', action: { kind: 'app', target: 'card-lost', toast: '카드 분실신고 화면으로 이동해요.' } } },
  { key: 'id', label: '주민등록번호·신분증', desc: '명의도용을 막기 위해 개인정보 노출 사실을 등록하세요.', button: { label: '개인정보노출자 등록 안내', action: { kind: 'info', toast: '개인정보노출자 등록 방법을 안내해요.' } } },
];

/**
 * @param {string} key
 * @param {{basis?: string, selected?: string[], newNoticeShown?: boolean}} ctx
 * @returns {{msgs?: Array, chips?: Array, multi?: boolean, input?: 'num'|'all'|'paste', newNotice?: boolean}}
 */
export function node(key, ctx) {
  const n = NODES[key];
  if (!n) throw new Error(`unknown node ${key}`);
  const out = n(ctx);
  // 신규 피싱(basis=llm)은 위험 분기의 마지막에 검토 등록 사실을 한 번 알립니다.
  if (out.terminal && ctx.basis === 'llm' && !ctx.newNoticeShown) {
    out.msgs = [...out.msgs, { kind: 'bot', text: '이 문자는 새로운 수법일 수 있어 검토 대상으로 등록했어요. 확인되면 다른 고객도 같은 문자로부터 보호받아요.' }];
    out.newNotice = true;
  }
  return out;
}

const NODES = {
  paste: () => ({ msgs: [{ kind: 'bot', text: '의심되는 문자를 붙여넣어 주세요. 링크는 누르지 말고, 문자를 길게 눌러 복사하면 돼요.' }], input: 'paste' }),
  // 위험: 피해 단계 질문
  stage: () => ({
    msgs: [{ kind: 'bot', text: '지금 어떤 상태인지 알려주세요.\n상황에 맞게 바로 도와드릴게요.' }],
    chips: [
      { label: '아무것도 안 했어요', go: 's1' },
      { label: '링크를 눌렀어요', go: 's2' },
      { label: '정보를 입력했어요', go: 's3' },
      { label: '돈을 보냈어요', go: 's4', style: 'urgent' },
    ],
  }),
  s1: () => ({ terminal: true, msgs: [{ kind: 'bot', text: '다행이에요. 링크는 누르지 말고 문자를 삭제하세요. 발신번호를 차단하면 같은 번호로 다시 오지 않아요.' }], chips: [{ label: '차단 방법 보기', go: 'block' }, REPORT, END[0]] }),
  block: () => ({ msgs: [{ kind: 'bot', text: '문자 앱에서 해당 대화를 열고 번호를 눌러 ‘차단’을 선택하면 돼요. 스팸 신고도 함께 하면 통신사 차단에 도움이 돼요.' }], chips: [REPORT, ...END] }),
  s2: () => ({ msgs: [{ kind: 'bot', text: '링크를 누른 뒤 앱이나 파일을 설치했나요?' }], chips: [{ label: '설치했어요', go: 's2i' }, { label: '설치 안 했어요', go: 's2n' }, { label: '잘 모르겠어요', go: 's2i' }] }),
  s2i: () => ({ terminal: true, msgs: [{ kind: 'bot', text: '설치된 앱이 정보를 빼낼 수 있어요. 비행기 모드로 바꾸고, 모르는 앱을 삭제한 뒤 보안 점검을 받으세요.' }], chips: [{ label: '앱 삭제 방법', action: { kind: 'info', toast: '설정에서 모르는 앱을 찾아 삭제하는 방법을 안내해요.' } }, CALL118, CS, ...END] }),
  s2n: () => ({ msgs: [{ kind: 'bot', text: '열린 페이지는 닫고 문자를 삭제하세요. 혹시 페이지에 정보를 입력했나요?' }], chips: [{ label: '입력 안 했어요', go: 's2ok' }, { label: '입력했어요', go: 's3' }] }),
  s2ok: () => ({ terminal: true, msgs: [{ kind: 'bot', text: '다행이에요. 문자를 삭제하고 발신번호를 차단해 두세요.' }], chips: [REPORT, ...END] }),
  s3: () => ({ msgs: [{ kind: 'bot', text: '어떤 정보를 입력했나요? 해당하는 걸 모두 골라주세요.' }], multi: true }),
  s3a: (ctx) => ({
    msgs: [
      { kind: 'bot', text: '고른 정보별로 지금 할 일을 안내할게요.' },
      { kind: 'acts', items: INPUT_INFO.filter((i) => ctx.selected?.includes(i.key)) },
      { kind: 'bot', text: '혹시 계좌에서 돈이 빠져나갔나요?' },
    ],
    chips: [{ label: '아니요', go: 's3no' }, { label: '네', go: 's4', style: 'urgent' }],
  }),
  s3no: () => ({ terminal: true, msgs: [{ kind: 'bot', text: '안내한 조치를 먼저 해 주세요. 이후에 모르는 출금이나 연락이 생기면 바로 다시 확인해 주세요.' }], chips: [REPORT, ...END] }),
  // 긴급: 지급정지 행동 전에는 종료 버튼을 띄우지 않습니다.
  s4: () => ({
    msgs: [
      { kind: 'alert', title: '지금 바로 지급정지를 신청해야 해요.', text: '빠를수록 돌려받을 가능성이 높아요.' },
      { kind: 'bot', text: '다른 은행 계좌에서 보냈다면 그 은행이나 112에 지급정지를 요청하세요.' },
    ],
    chips: [
      { label: '지급정지 신청하기', style: 'urgent', action: { kind: 'app', target: 'payment-stop', toast: '우리WON뱅킹 지급정지 신청 화면으로 이동해요.' }, then: 's4done' },
      CALL112,
      CS,
    ],
  }),
  s4done: () => ({ terminal: true, msgs: [{ kind: 'bot', text: '지급정지 후에는 피해구제 신청이 필요해요.' }], chips: [{ label: '피해구제 신청 안내', action: { kind: 'info', toast: '피해구제 신청 서류와 절차를 안내해요.' } }, ...END] }),

  // 위험 징후 없음
  safeNext: () => ({ msgs: [{ kind: 'bot', text: '그래도 이후에 인증번호나 송금을 요구하는\n연락이 오면 응답하지 말고 다시 확인해 주세요.' }], chips: [END[0], { label: '그래도 의심돼요', go: 'doubt' }, END[1]] }),
  doubt: () => ({ msgs: [{ kind: 'bot', text: '어떤 점이 의심되나요?' }], chips: [{ label: '추가 문자를 받았어요', go: 'paste' }, { label: '전화가 왔어요', go: 'call' }, { label: '그냥 신고할게요', go: 'report' }] }),
  call: () => ({ msgs: [{ kind: 'bot', text: '금융기관은 전화로 비밀번호나 인증번호를 묻지 않아요. 통화를 끊고 공식 번호로 직접 확인하세요.' }], chips: [CS, CALL112, ...END] }),

  // 낮은 위험 (Figma woori_result_low_risk)
  cautionNext: () => ({
    msgs: [{ kind: 'bot', text: '일부 확인이 필요한 내용이 있어요.\n공식 채널에서 확인한 뒤 다음 행동을 결정해요.' }],
    chips: cautionChips(),
  }),
  officialHow: () => ({ msgs: [{ kind: 'bot', text: '문자에 적힌 번호 말고, 기관 공식 앱이나 홈페이지에 나온 대표번호로 직접 연락해 확인하세요.' }], chips: [...END] }),
  checkOrg: () => ({ msgs: [{ kind: 'bot', text: '문자에 기관 이름이 있다면 그 기관의 공식 앱에서 같은 안내가 있는지 확인하세요. 기관 이름이 없다면 응답하지 않는 게 안전해요.' }], chips: [{ label: '추가 내용 보내기', go: 'addAll' }, ...END] }),

  // 정보 부족 (Figma woori_result_no_data)
  noDataNext: () => ({
    msgs: [{ kind: 'bot', text: '지금 정보만으로는 위험 여부를 판단하기 어려워요.\n텍스트 원문을 보내주시면 다시 확인할게요.' }],
    chips: noDataChips(),
  }),
  neededInfo: () => ({ msgs: [{ kind: 'list', title: '이런 정보가 있으면 정확해져요', items: ['앞뒤 내용이 포함된 텍스트 원문', '텍스트 속 URL 주소(누르지 말고 복사)'] }], chips: noDataChips() }),

  // 재분석 후에도 판단이 어려울 때
  unknownFinal: () => ({ msgs: [{ kind: 'bot', text: '여전히 판단하기 어려워요. 문자에 나온 기관의 공식 앱이나 대표번호로 직접 확인하는 게 가장 안전해요.' }], chips: [CALL118, REPORT, END[1]] }),
  addNum: () => ({ msgs: [{ kind: 'bot', text: '문자를 보낸 번호를 입력해 주세요.' }], input: 'num' }),
  addAll: () => ({ msgs: [{ kind: 'bot', text: '받은 문자 전체를 다시 붙여넣어 주세요. 앞뒤 내용까지 있으면 더 정확해요.' }], input: 'all' }),
  tips: () => ({ msgs: [{ kind: 'bot', text: '의심 문자는 링크를 누르지 말고, 답장이나 전화도 하지 마세요. 기관 이름이 있다면 공식 앱이나 대표번호로 직접 확인하세요.' }], chips: [REPORT, END[0]] }),
  prevent: () => ({ msgs: [{ kind: 'list', title: '스미싱 예방 수칙', items: ['모르는 번호가 보낸 링크는 누르지 마세요.', '금융기관은 문자로 비밀번호나 인증번호를 묻지 않아요.', '의심되면 공식 앱이나 대표번호로 직접 확인하세요.'] }], chips: [{ label: '문자 확인하기', go: 'paste' }] }),

  // 신고
  // 실제 백엔드에는 신고 API가 없어서, 연결된 경우 118·스팸 신고 안내로 대신합니다.
  report: () => (reportSupported
    ? { msgs: [{ kind: 'bot', text: '이 문자를 피싱 의심으로 신고할까요? 이름이나 계좌번호 같은 개인정보는 가린 뒤 저장돼요.' }], chips: [{ label: '신고하기', go: 'reportSubmit', style: 'primary' }, { label: '취소', go: 'reportCancel' }] }
    : { msgs: [{ kind: 'bot', text: '앱 안 신고 기능은 준비 중이에요. 휴대폰 문자 앱의 스팸 신고나 118로 신고하면 같은 문자가 더 빨리 차단돼요.' }], chips: [CALL118, { label: '118 신고 방법', action: { kind: 'info', toast: '문자 앱의 스팸 신고와 118 신고 방법을 안내해요.' } }, ...END] }),
  reportDone: () => ({ msgs: [{ kind: 'bot', text: '신고가 접수됐어요. 검토 후 다른 고객 보호에 활용할게요. 휴대폰의 스팸 신고나 118 신고도 함께 하면 더 빨리 차단돼요.' }], chips: [{ label: '118 신고 방법', action: { kind: 'info', toast: '문자 앱의 스팸 신고와 118 신고 방법을 안내해요.' } }, ...END] }),
  reportCancel: () => ({ msgs: [{ kind: 'bot', text: '신고를 취소했어요.' }], chips: END }),
  reportFail: () => ({ msgs: [{ kind: 'bot', text: '신고를 접수하지 못했어요. 잠시 후 다시 시도해 주세요.' }], chips: [{ label: '다시 신고하기', go: 'reportSubmit' }, END[1]] }),

  // 예외
  empty: () => ({ msgs: [{ kind: 'bot', text: '텍스트 내용이 확인되지 않아요. 받은 텍스트 전체를 붙여넣어 주세요.' }], chips: [{ label: '다시 붙여넣기', go: 'paste' }] }),
  tooShort: () => ({ msgs: [{ kind: 'bot', text: '텍스트 내용이 너무 짧아 확인하기 어려워요. 받은 텍스트 전체를 붙여넣어 주세요.' }], chips: [{ label: '다시 붙여넣기', go: 'paste' }] }),
  tooLong: () => ({ msgs: [{ kind: 'bot', text: '내용이 너무 길어요. 의심되는 문자 하나만 보내 주세요.' }], chips: [{ label: '다시 붙여넣기', go: 'paste' }] }),
  question: () => ({ msgs: [{ kind: 'bot', text: '저는 받은 문자가 위험한지 확인해 드려요. 확인할 문자를 보내 주세요.' }], chips: [{ label: '스미싱 예방 수칙', go: 'prevent' }, { label: '문자 확인하기', go: 'paste' }] }),
  error: () => ({ msgs: [{ kind: 'alert', tone: 'neutral', title: '지금은 정확한 분석이 어려워요.', text: '링크는 누르지 말고 잠시 후 다시 시도해 주세요.' }], chips: [{ label: '다시 시도', go: 'retry' }, { label: '대처법 보기', go: 'tips' }] }),
};

function cautionChips() {
  return [
    { label: '공식 확인 방법', go: 'officialHow' },
    { label: '기관 확인하기', go: 'checkOrg' },
    { label: '추가 내용 보내기', go: 'addAll' },
    { label: '주의사항 보기', go: 'tips' },
  ];
}
function noDataChips() {
  return [
    { label: '텍스트 원문 보내기', go: 'addAll' },
    { label: '필요한 정보 보기', go: 'neededInfo' },
  ];
}

/** 입력 검증. 통과하면 null, 아니면 예외 노드 키를 돌려줍니다. */
export function checkInput(text) {
  const t = text.trim();
  if (!t) return 'empty';
  if (t.length > 2000) return 'tooLong';
  const hasLinkOrNum = /(https?:\/\/|www\.|bit\.ly|\d{2,4}-\d{3,4}-\d{4})/.test(t);
  if (!hasLinkOrNum && t.length < 60 && (/[?？]$/.test(t) || /뭐야|뭐예요|뭔가요|어떻게|알려줘/.test(t))) return 'question';
  if (t.length < 8) return 'tooShort';
  return null;
}

/** 판정 결과 뒤에 이어질 노드 */
export function nextAfterResult(status) {
  return { RISK: 'stage', SAFE: 'safeNext', CAUTION: 'cautionNext', NO_DATA: 'noDataNext', UNKNOWN: 'noDataNext' }[status] || 'noDataNext';
}
