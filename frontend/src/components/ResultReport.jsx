import { fig } from '../assets.js';

// 결과 리포트 (Figma: woori_result_report 19:2 · woori_result_safe 54:2 · woori_result_low_risk 54:108 · woori_result_no_data 75:2)
// status: RISK | SAFE | CAUTION | NO_DATA  (예전 UNKNOWN은 NO_DATA로 처리)

const COPY = {
  RISK: {
    badge: 'RISK · 위험 의심',
    title: '스미싱 위험이 의심돼요',
    warnTitle: '링크를 누르지 마세요',
    section: '주요 위험 신호',
    actTitle: '지금 이렇게 해주세요',
    actions: [
      '링크를 누르지 말고, 발신처를 공식 앱에서 확인하세요.',
      '개인정보나 인증번호를 입력하지 마세요.',
      '이미 눌렀다면 앱 설치·정보 입력 여부를 확인하세요.',
    ],
    actNote: '금융 피해가 발생했다면 거래 금융회사에도 즉시 연락하세요.',
  },
  SAFE: {
    badge: 'SAFE · 위험 징후 없음',
    title: '위험 징후가 발견되지 않았어요',
    warnTitle: '지금은 위험 신호가 보이지 않아요',
    warnText: '안전하다고 단정하진 않아요. 이후 연락에는 계속 주의하세요.',
    section: '이렇게 확인했어요',
    actTitle: '그래도 이렇게 확인하세요',
    actions: [
      '인증번호나 비밀번호를 묻는 연락에는 응답하지 마세요.',
      '송금을 요구하는 추가 문자가 오면 다시 확인해 주세요.',
      '결제 내역은 우리카드 앱에서 직접 확인하세요.',
    ],
    actNote: '근거가 충분할 때만 ‘위험 징후 없음’으로 안내해요.',
  },
  CAUTION: {
    badge: 'CAUTION · 낮은 위험',
    title: '일부 주의 신호가 보여요',
    warnTitle: '내용을 한 번 더 확인해 주세요',
    warnText: '일부 주의 신호가 있지만 사기로 단정할 수는 없어요.',
    section: '확인이 필요한 신호',
    actTitle: '공식 채널로 확인해 주세요',
    actions: [
      '문자 속 번호로 전화하거나 답장하지 마세요.',
      '기관 이름이 있다면 공식 앱·대표번호로 직접 확인하세요.',
      '발신번호나 문자 전체를 보내주시면 다시 분석할게요.',
    ],
    actNote: '낮은 위험은 안전 보장이 아니에요. 공식 채널로 한 번 더 확인하세요.',
  },
  NO_DATA: {
    badge: 'NO DATA · 정보 부족',
    title: '분석할 정보가 부족해요',
    warnTitle: '정보를 더 보내주시면 확인할게요',
    warnText: '분석 정보나 참고 데이터가 부족해 판단을 보류해요.',
    section: '추가로 필요한 정보',
    actTitle: '이 정보를 보내주세요',
    actions: [
      '앞뒤 내용이 포함된 문자 전체를 보내주세요.',
      'URL은 누르지 말고 주소 그대로 복사해주세요.',
      '이미지는 글자가 선명하게 보이도록 올려주세요.',
    ],
    actNote: '정보·데이터 부족은 위험이 낮거나 안전하다는 뜻이 아니에요.',
  },
};

export const normalizeStatus = (s) => (s === 'UNKNOWN' ? 'NO_DATA' : s in COPY ? s : 'NO_DATA');

const FACE_IMG = { RISK: 'face-risk.png', SAFE: 'face-safe.png', CAUTION: 'face-caution.png', NO_DATA: 'face-nodata.png' };
const FACTOR_IMG = { url: 'factor-url.png', urgency: 'factor-urgent.png', impersonation: 'factor-imperson.png' };

const Check = ({ size = 10, color }) => (
  <svg width={size} height={size * 0.75} viewBox="0 0 10 7.5" fill="none" aria-hidden="true">
    <path d="M1 4.1L3.8 6.5L9 1" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
);
const Triangle = ({ color }) => (
  <svg width="11" height="9.5" viewBox="0 0 12 10.8" fill="none" aria-hidden="true">
    <path d="M6 0.8L11.4 10H0.6Z" stroke={color} strokeWidth="1.6" strokeLinejoin="round" />
  </svg>
);

function FactorMark({ code, status }) {
  if (status === 'SAFE') return <span className="factor__mark"><Check size={9} color="#1e9a52" /></span>;
  if (status === 'CAUTION') return <span className="factor__mark"><Triangle color="#e59800" /></span>;
  if (status === 'NO_DATA') return <span className="factor__mark factor__mark--text">?</span>;
  return <span className="factor__mark"><img src={fig(FACTOR_IMG[code] || FACTOR_IMG.url)} alt="" /></span>;
}

function useCopy(result) {
  const s = normalizeStatus(result.status);
  return { s, c: COPY[s], tone: s.toLowerCase().replace('_', '-') };
}

// 1단계: 결과 카드 (Figma 결과 화면)
export function ResultCard({ result }) {
  const { s, c, tone } = useCopy(result);
  const warnText = s === 'RISK'
    ? (result.basis === 'entities' || result.basis === 'safe_browsing'
      ? '이미 신고된 피싱 사이트 주소예요. 링크는 열지 말고 확인하세요.'
      : '문자만으로 확정할 수 없어도, 링크는 열지 말고 확인하세요.')
    : c.warnText;
  return (
    <section className={`rcard rcard--${tone}`} aria-label="AI 분석 결과">
      <div className="rcard__head">
        <span className="rcard__face" aria-hidden="true"><img src={fig(FACE_IMG[s])} alt="" /></span>
        <div className="rcard__heading">
          <p className="rcard__label">AI 분석 결과</p>
          <h2 className="rcard__title">{c.title}</h2>
        </div>
        <span className="rbadge"><i className="rbadge__dot" aria-hidden="true" />{c.badge}</span>
      </div>
      <div className="warn">
        <span className="warn__circle" aria-hidden="true">
          {s === 'SAFE' ? <Check size={10} color="#ffffff" /> : s === 'NO_DATA' ? '?' : '!'}
        </span>
        <div>
          <p className="warn__title">{c.warnTitle}</p>
          <p className="warn__text">{warnText}</p>
        </div>
      </div>
      <p className="rcard__section">{c.section}</p>
      <ul className="factors">
        {result.reasons.map((r, i) => (
          <li key={i} className="factor">
            <FactorMark code={r.code} status={s} />
            <span className="factor__title">{r.title}</span>
            {r.detail && <span className="factor__detail">{r.detail}</span>}
          </li>
        ))}
      </ul>
    </section>
  );
}

// 2단계: '다음 행동 확인하기'를 누른 뒤 나오는 행동 안내 카드 (Figma *_next 화면)
export function ActionCard({ result }) {
  const { c } = useCopy(result);
  return (
    <section className="action-card">
      <div className="action-card__head">
        <img className="action-card__icon" src={fig('action-icon.png')} alt="" />
        <h3>{c.actTitle}</h3>
      </div>
      <ul>{c.actions.map((a) => <li key={a}>{a}</li>)}</ul>
      <p className="action-card__note">{c.actNote}</p>
    </section>
  );
}
