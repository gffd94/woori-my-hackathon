import { useRef } from 'react';
import Ico from './Ico.jsx';

// 하단 입력창 (19:125)
export default function InputBar({ value, onChange, onSend, onPaste, placeholder, disabled }) {
  const ref = useRef(null);
  const send = () => { if (!disabled) onSend(); };
  return (
    <div className="inputbar">
      <div className="inputbar__area">
        <div className="inputbar__field">
          <textarea
            ref={ref}
            value={value}
            onChange={(e) => onChange(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); send(); } }}
            placeholder={placeholder || '확인할 텍스트를 보내주세요.'}
            aria-label="확인할 텍스트"
          />
          <div className="inputbar__tools">
            <button className="inputbar__tool" onClick={async () => { await onPaste(); ref.current?.focus(); }} aria-label="붙여넣기">
              <Ico name="input-btn-bg.svg" w={26} h={26} />
              <Ico name="input-clip.svg" w={10.72} h={10.06} inset="-6.96% -6.53%" className="abs" style={{ left: 7.94, top: 8 }} />
            </button>
            <span className="inputbar__hint">텍스트 붙여넣기</span>
            <button className="inputbar__send" onClick={send} disabled={disabled} aria-label="보내기">
              <Ico name="send-bg.svg" w={40} h={40} />
              <Ico name="send-arrow.svg" w={14} h={16} inset="-6.43% -7.5%" className="abs" style={{ left: 13, top: 12 }} />
            </button>
          </div>
        </div>
        <p className="inputbar__foot">WON 안심톡 · 위험 신호를 분석하고 다음 행동을 안내해요.</p>
      </div>
    </div>
  );
}
