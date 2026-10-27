import { useEffect, useState } from 'react';
import Ico from './Ico.jsx';
import Avatar from './Avatar.jsx';

// 첫 안내 (Figma 19:113)
export function Greeting() {
  return (
    <div className="row row--greet">
      <Avatar size={38} />
      <div className="bubble bubble--greet">
        <p className="bubble__title">안녕하세요! 저는 위비예요.</p>
        <p className="bubble__body">확인할 텍스트를 보내주세요.<br />링크와 문구의 위험 신호를 살펴볼게요.</p>
        <p className="bubble__small">개인정보를 자동으로 가린 뒤 분석해요.</p>
      </div>
    </div>
  );
}

// 안전 문구 (Figma 19:118)
export function SafetyGuide() {
  return (
    <section className="guide">
      <div className="guide__head">
        <span className="guide__badge" aria-hidden="true">
          <Ico name="guide-badge.svg" w={24} h={24} />
          <Ico name="guide-shield.svg" w={12} h={15} className="abs" style={{ left: 6, top: 5 }} />
          <Ico name="guide-check.svg" w={5.5} h={4} inset="-13.75% -10%" className="abs" style={{ left: 9.5, top: 9.5 }} />
        </span>
        <h2>안전하게 확인하려면</h2>
      </div>
      <ul>
        <li>텍스트 원문과 URL을 함께 보내주세요.</li>
        <li>주민번호·계좌번호·인증번호는 자동으로 가려요.</li>
      </ul>
      <p className="guide__note">링크를 열지 않고 문구와 주소부터 확인해요.</p>
    </section>
  );
}

const URL_RE = /(https?:\/\/\S+|www\.\S+|bit\.ly\/\S+)/i;

// 고객 input · 고객 문자 내용 (Figma 19:119, 19:120). 링크는 열리지 않게 텍스트로만 보여줍니다.
export function ReceivedMessage({ text, time, shared, maskedCount = 0 }) {
  const url = (text.match(URL_RE) || [])[0];
  const body = (url ? text.replace(url, '') : text).trim().split('\n').filter(Boolean);
  return (
    <div className="received">
      <p className="received__label">
        {shared ? '공유한 텍스트' : '받은 텍스트'} · {time}
        {maskedCount > 0 && <span className="received__masked"> · 개인정보 {maskedCount}건 자동 가림</span>}
      </p>
      {body.map((line, i) => (
        <p key={i} className={i === 0 ? 'received__first' : 'received__line'}>{line}</p>
      ))}
      {url && (
        <div className="received__url" title="링크는 열리지 않아요">
          <Ico name="url-arrow.svg" w={8} h={8} inset="-8.75%" />
          <span>{url}</span>
        </div>
      )}
      <p className="received__time">{time}</p>
    </div>
  );
}

// 분석 중 말풍선 (Figma 컴포넌트 '분석 중 말풍선' 108:42 · B안 진행 바형)
// 단계=1→2→3→1 을 1.4초마다 돌립니다. 아래 왼쪽 태그는 그 단계에서 실제로 쓰는 기술입니다.
export const ANALYZE_STEPS = [
  { text: '개인정보를 가리고\n링크를 조회하고 있어요', tag: '자동 마스킹 · 피싱 DB 조회', next: '다음: 신종 수법 비교' },
  { text: 'AI를 통해 요즘 유행하는\n신종 수법과 비교 중이에요', tag: '신종 수법 DB · 벡터 검색', next: '다음: 위험 이유 정리' },
  { text: '위험한 이유를 정리하고 있어요', tag: 'LLM · RAG', next: '곧 결과를 알려드릴게요' },
];
const STEP_MS = 1400;

export function Analyzing() {
  const [step, setStep] = useState(0);
  useEffect(() => {
    const t = setInterval(() => setStep((i) => (i + 1) % ANALYZE_STEPS.length), STEP_MS);
    return () => clearInterval(t);
  }, []);
  const cur = ANALYZE_STEPS[step];
  const total = ANALYZE_STEPS.length;
  return (
    <div className="analyzing">
      <div className="row row--tight">
        <Avatar size={34} />
        <div className="bubble bubble--analyzing">
          <div className="analyzing__head">
            <span className="analyzing__ai">AI</span>
            <span className="analyzing__status">위비 AI가 분석 중 · {step + 1}/{total}</span>
          </div>
          <p key={step} className="analyzing__text" role="status" aria-live="polite">{cur.text}</p>
          <div className="analyzing__track" aria-hidden="true">
            <span className="analyzing__bar" style={{ width: `${((step + 1) / total) * 100}%` }} />
          </div>
          <div className="analyzing__foot">
            <span className="analyzing__tag">{cur.tag}</span>
            <span className="analyzing__next">{cur.next}</span>
          </div>
        </div>
      </div>
      <p className="analyzing__caption">위비 프렌즈와 함께 안전하게 확인해요</p>
    </div>
  );
}

export function TypingDots() {
  return (
    <div className="bubble bubble--bot bubble--typing" aria-label="입력 중">
      <span className="dots" aria-hidden="true">
        <Ico name="dot-1.svg" w={4.2} h={4.2} />
        <Ico name="dot-2.svg" w={4.2} h={4.2} />
        <Ico name="dot-3.svg" w={4.2} h={4.2} />
      </span>
    </div>
  );
}

// 이하 대화 메시지: Figma 말풍선 스타일을 따라 확장
export function BotText({ text }) {
  return <div className="bubble bubble--bot">{text}</div>;
}

export function BotList({ title, items }) {
  return (
    <div className="bubble bubble--bot">
      <p className="bubble__title">{title}</p>
      <ul className="bubble__list">{items.map((t) => <li key={t}>{t}</li>)}</ul>
    </div>
  );
}

export function BotAlert({ title, text, tone = 'risk' }) {
  return (
    <div className={`alert alert--${tone}`}>
      {tone === 'risk' && (
        <span className="alert__icon" aria-hidden="true">
          <Ico name="warn-circle.svg" w={20} h={20} />
          <b>!</b>
        </span>
      )}
      <div>
        <p className="alert__title">{title}</p>
        <p className="alert__text">{text}</p>
      </div>
    </div>
  );
}

export function BotActions({ items, onAction, disabled }) {
  return (
    <div className="bubble bubble--bot acts">
      {items.map((i) => (
        <div key={i.key} className="acts__item">
          <p className="acts__name">{i.label}</p>
          <p className="acts__desc">{i.desc}</p>
          <button className="chip" onClick={() => onAction(i.button)} disabled={disabled}>{i.button.label}</button>
        </div>
      ))}
    </div>
  );
}

export function UserEcho({ text }) {
  return <div className="echo">{text}</div>;
}

export function Chips({ buttons, onPick, frozen, chosen }) {
  return (
    <div className="chips">
      {buttons.map((b, i) => (
        <button
          key={b.label + i}
          className={`chip${b.style ? ` chip--${b.style}` : ''}${chosen === i ? ' chip--chosen' : ''}`}
          disabled={frozen}
          onClick={() => onPick(b, i)}
        >
          {b.label}
        </button>
      ))}
    </div>
  );
}

export function MultiSelect({ options, frozen, onDone }) {
  const [sel, setSel] = useState([]);
  const toggle = (k) => setSel((s) => (s.includes(k) ? s.filter((x) => x !== k) : [...s, k]));
  return (
    <div className="chips">
      {options.map((o) => (
        <button key={o.key} className={`chip${sel.includes(o.key) ? ' chip--selected' : ''}`}
          aria-pressed={sel.includes(o.key)} disabled={frozen} onClick={() => toggle(o.key)}>
          {o.label}
        </button>
      ))}
      <button className="chip chip--primary" disabled={frozen || !sel.length} onClick={() => onDone(sel)}>선택 완료</button>
    </div>
  );
}

// 위비 말풍선 줄: 연속된 봇 메시지 중 첫 번째에만 프로필을 보여줍니다.
export function BotRow({ showAvatar, children }) {
  return (
    <div className="bot-row">
      {showAvatar ? <Avatar size={38} /> : <span className="bot-row__spacer" aria-hidden="true" />}
      <div className="bot-row__body">{children}</div>
    </div>
  );
}
