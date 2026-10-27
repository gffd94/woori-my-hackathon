// 우리WON뱅킹 네이티브 앱과 연결하는 지점입니다.
// 앱 WebView가 window.WooriBridge.run(action)을 제공하면 그쪽으로 넘기고,
// 브라우저에서 단독 실행할 때는 외부 링크만 열고 나머지는 화면 안내(토스트)로 대신합니다.
//   action = { kind: 'app' | 'tel' | 'link' | 'info', target?: string, toast: string }
//   app 대상: 'payment-stop'(지급정지), 'password-change', 'card-lost'
//   tel 대상: '112', '118', 'WOORI_CS'(고객센터 번호는 앱에서 결정)
export function runAction(action) {
  const bridge = typeof window !== 'undefined' ? window.WooriBridge : null;
  if (bridge && typeof bridge.run === 'function') {
    bridge.run(action);
    return;
  }
  if (action.kind === 'link' && action.target) window.open(action.target, '_blank', 'noopener');
}

// 공유하기 진입: 앱이 문자 앱의 공유 내용을 받아 ?shared=<문자 내용> 으로 이 화면을 엽니다.
export function readSharedText() {
  if (typeof window === 'undefined') return '';
  return new URLSearchParams(window.location.search).get('shared') || '';
}

// 백엔드 없이 시연할 때: ?sample=known | newRisk | safe | unknown
export function readSampleKey() {
  if (typeof window === 'undefined') return '';
  return new URLSearchParams(window.location.search).get('sample') || '';
}
