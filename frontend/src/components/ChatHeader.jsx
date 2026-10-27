import Ico from './Ico.jsx';

// 상단 바 (Figma 19:123)
export default function ChatHeader({ onBack, onClose }) {
  return (
    <header className="chat-header">
      <button className="chat-header__btn" onClick={onBack} aria-label="뒤로">
        <Ico name="icon-back.svg" w={14} h={16} inset="-5.62% -6.43%" />
      </button>
      <span className="chat-header__icon" aria-hidden="true">
        <Ico name="header-icon-bg.svg" w={34} h={34} />
        <Ico name="header-shield.svg" w={16} h={21} className="abs" style={{ left: 9, top: 7 }} />
        <Ico name="header-check.svg" w={7} h={5} inset="-18% -12.86%" className="abs" style={{ left: 13.5, top: 14 }} />
      </span>
      <div className="chat-header__text">
        <h1>우리WON 안심톡</h1>
        <p>보내주신 내용의 위험 신호를 함께 확인해요</p>
      </div>
      <button className="chat-header__btn chat-header__close" onClick={onClose} aria-label="닫기">
        <Ico name="icon-close.svg" w={12} h={12} inset="-6.67%" />
      </button>
    </header>
  );
}
