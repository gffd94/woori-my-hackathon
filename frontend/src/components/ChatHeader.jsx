import Ico from './Ico.jsx';
import Avatar from './Avatar.jsx';

// 상단 바 (Figma 19:123)
export default function ChatHeader({ onBack, onClose }) {
  return (
    <header className="chat-header">
      <button className="chat-header__btn" onClick={onBack} aria-label="뒤로">
        <Ico name="icon-back.svg" w={14} h={16} inset="-5.62% -6.43%" />
      </button>
      <span className="chat-header__icon" aria-hidden="true">
        <Avatar size={34} />
      </span>
      <div className="chat-header__text">
        <h1>위비 레이더</h1>
        <p>보내주신 내용의 위험 신호를 함께 확인해요</p>
      </div>
      <button className="chat-header__btn chat-header__close" onClick={onClose} aria-label="닫기">
        <Ico name="icon-close.svg" w={12} h={12} inset="-6.67%" />
      </button>
    </header>
  );
}
