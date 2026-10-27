import { useCallback, useEffect, useRef, useState } from 'react';
import ChatHeader from '../components/ChatHeader.jsx';
import InputBar from '../components/InputBar.jsx';
import Toast from '../components/Toast.jsx';
import { ResultCard, ActionCard } from '../components/ResultReport.jsx';
import {
  Greeting, SafetyGuide, ReceivedMessage, Analyzing,
  BotText, BotList, BotAlert, BotActions, UserEcho, Chips, MultiSelect, TypingDots, BotRow,
} from '../components/Messages.jsx';
import { analyze, report } from '../api/client.js';
import { SAMPLES } from '../api/mock.js';
import { node, checkInput, nextAfterResult, INPUT_INFO } from '../flow/dialogue.js';
import { runAction, readSampleKey } from '../bridge.js';
import { maskPersonalInfo } from '../utils/mask.js';

const wait = (ms) => new Promise((r) => setTimeout(r, ms));
const timeNow = () => {
  const d = new Date();
  const h = d.getHours();
  return `${h < 12 ? '오전' : '오후'} ${h % 12 || 12}:${String(d.getMinutes()).padStart(2, '0')}`;
};
const PLACEHOLDER = { num: '예: 010-1234-5678', all: '받은 문자 전체를 붙여넣어 주세요.' };
const BOT_TYPES = ['bot', 'list', 'alert', 'acts', 'typing'];
let seq = 0;
const id = () => ++seq;

function initialItems() {
  return [
    { id: id(), type: 'time', time: timeNow() },
    { id: id(), type: 'greeting' },
    { id: id(), type: 'guide' },
  ];
}

export default function ChatScreen({ onExit, sharedText }) {
  const [items, setItems] = useState(initialItems);
  const [value, setValue] = useState('');
  const [mode, setMode] = useState(null); // null | 'paste' | 'num' | 'all'
  const [busy, setBusy] = useState(false);
  const [toast, setToast] = useState('');
  const ctx = useRef({ basis: null, retry: 0, lastText: '', source: 'paste', newNoticeShown: false });
  const listRef = useRef(null);
  const toastTimer = useRef(null);

  const push = useCallback((...add) => setItems((prev) => [...prev, ...add.map((x) => ({ id: id(), ...x }))]), []);
  const removeType = useCallback((type) => setItems((prev) => prev.filter((x) => x.type !== type)), []);
  const freeze = useCallback((chosen) => setItems((prev) => prev.map((x) =>
    (x.type === 'chips' || x.type === 'multi' || x.type === 'acts' || x.type === 'nextBtn') && !x.frozen
      ? { ...x, frozen: true, chosen: x.type === 'chips' ? chosen : undefined }
      : x)), []);

  const showToast = useCallback((msg) => {
    setToast(msg);
    clearTimeout(toastTimer.current);
    toastTimer.current = setTimeout(() => setToast(''), 2400);
  }, []);

  useEffect(() => {
    listRef.current?.scrollTo({ top: listRef.current.scrollHeight, behavior: 'smooth' });
  }, [items]);

  // 노드의 메시지를 타이핑 표시와 함께 순서대로 띄웁니다.
  const runNode = useCallback(async (key) => {
    if (key === 'restart') { ctx.current = { basis: null, retry: 0, lastText: '', source: 'paste', newNoticeShown: false }; setItems(initialItems()); setMode(null); return; }
    if (key === 'retry') { startAnalysis(ctx.current.lastText, { source: ctx.current.source, silent: true }); return; }
    if (key === 'reportSubmit') {
      setBusy(true);
      try { await report({ text: ctx.current.lastText, source: ctx.current.source }); await runNode('reportDone'); }
      catch { await runNode('reportFail'); }
      finally { setBusy(false); }
      return;
    }
    const n = node(key, ctx.current);
    if (n.newNotice) ctx.current.newNoticeShown = true;
    setBusy(true);
    for (const m of n.msgs || []) {
      push({ type: 'typing' });
      await wait(420);
      removeType('typing');
      push({ type: m.kind, ...m });
    }
    if (n.chips) push({ type: 'chips', buttons: n.chips });
    if (n.multi) push({ type: 'multi' });
    setMode(n.input || null);
    setBusy(false);
  }, [push, removeType]); // eslint-disable-line react-hooks/exhaustive-deps

  // 결과 카드 먼저 → '다음 행동 확인하기' 버튼 → 누르면 행동 안내와 다음 선택지
  const showResult = useCallback(async (result) => {
    ctx.current.basis = result.basis || null;
    push({ type: 'report', result });
    await wait(250);
    push({ type: 'nextBtn', result });
  }, [push]);

  const onNextStep = useCallback(async (result) => {
    freeze();
    push({ type: 'user', text: '다음 행동 확인하기' });
    await wait(250);
    push({ type: 'actions', result });
    await wait(300);
    const undecided = result.status !== 'RISK' && result.status !== 'SAFE';
    // 정보를 덧붙여 2번 다시 봐도 판단이 어려우면 공식 채널 확인으로 안내
    await runNode(undecided && ctx.current.retry >= 2 ? 'unknownFinal' : nextAfterResult(result.status));
  }, [freeze, push, runNode]);

  const startAnalysis = useCallback(async (raw, { source = 'paste', shared = false, silent = false } = {}) => {
    // 고객이 가리지 않고 보내도 개인정보를 먼저 자동으로 가린 뒤 화면 표시·분석에 사용
    const masked = silent ? { text: raw, count: 0 } : maskPersonalInfo(raw);
    const text = masked.text;
    ctx.current = { ...ctx.current, basis: null, retry: 0, lastText: text, source, newNoticeShown: false };
    setMode(null);
    setBusy(true);
    if (!silent) push({ type: 'received', text, time: timeNow(), shared, maskedCount: masked.count });
    push({ type: 'analyzing' });
    try {
      const result = await analyze({ text, source });
      removeType('analyzing');
      await showResult(result);
    } catch {
      removeType('analyzing');
      await runNode('error');
    } finally {
      setBusy(false);
    }
  }, [push, removeType, runNode, showResult]);

  // 추가 확인 필요 → 정보 추가 후 재분석 (최대 2회)
  const reanalyze = useCallback(async (extra) => {
    ctx.current.retry += 1;
    const combined = `${ctx.current.lastText}\n${maskPersonalInfo(extra).text}`;
    ctx.current.lastText = combined;
    setMode(null);
    setBusy(true);
    push({ type: 'analyzing', again: true });
    try {
      const result = await analyze({ text: combined, source: ctx.current.source });
      removeType('analyzing');
      await showResult(result);
    } catch {
      removeType('analyzing');
      await runNode('error');
    } finally {
      setBusy(false);
    }
  }, [push, removeType, runNode, showResult]);

  // 공유하기로 들어온 경우 바로 분석
  const sharedOnce = useRef(false);
  useEffect(() => {
    if (sharedOnce.current) return;
    const sample = SAMPLES[readSampleKey()];
    if (sharedText || sample) {
      sharedOnce.current = true;
      startAnalysis(sharedText || sample, { source: sharedText ? 'share' : 'paste', shared: !!sharedText });
    }
  }, [sharedText, startAnalysis, freeze]);

  const doAction = useCallback((a) => { showToast(a.toast); runAction(a); }, [showToast]);

  const onPick = useCallback((b, i) => {
    if (busy) return;
    if (b.action) {
      doAction(b.action);
      if (b.then) { freeze(i); runNode(b.then); }
      return;
    }
    freeze(i);
    push({ type: 'user', text: b.label });
    runNode(b.go);
  }, [busy, doAction, freeze, push, runNode, startAnalysis]);

  const onSend = useCallback(() => {
    const text = value.trim();
    setValue('');
    freeze();
    if (mode === 'num' || mode === 'all') {
      if (!text) { runNode(mode === 'num' ? 'addNum' : 'addAll'); return; }
      push({ type: 'user', text });
      reanalyze(text);
      return;
    }
    const bad = checkInput(text);
    if (bad) {
      if (text) push({ type: 'user', text: text.length > 80 ? `${text.slice(0, 80)}…` : text });
      runNode(bad);
      return;
    }
    startAnalysis(text, { source: 'paste' });
  }, [value, mode, freeze, push, reanalyze, runNode, startAnalysis]);

  const onPaste = useCallback(async () => {
    try {
      const t = await navigator.clipboard.readText();
      if (t) setValue(t);
    } catch {
      showToast('입력창을 길게 눌러 붙여넣어 주세요.');
    }
  }, [showToast]);

  return (
    <div className="screen chat">
      <ChatHeader onBack={onExit} onClose={onExit} />
      <Toast message={toast} />
      <div className="chat__list" ref={listRef}>
        {items.map((it, idx) => {
          const prev = items[idx - 1];
          const showAvatar = !prev || !BOT_TYPES.includes(prev.type);
          const wrap = (el) => <BotRow key={it.id} showAvatar={showAvatar}>{el}</BotRow>;
          switch (it.type) {
            case 'time': return <p key={it.id} className="timepill">오늘 {it.time}</p>;
            case 'greeting': return <Greeting key={it.id} />;
            case 'guide': return <SafetyGuide key={it.id} />;
            case 'received': return <ReceivedMessage key={it.id} text={it.text} time={it.time} shared={it.shared} maskedCount={it.maskedCount} />;
            case 'analyzing': return <Analyzing key={it.id} />;
            case 'report': return <ResultCard key={it.id} result={it.result} />;
            case 'nextBtn': return it.frozen ? null : (
              <button key={it.id} className="next-btn" disabled={busy} onClick={() => onNextStep(it.result)}>
                다음 행동 확인하기 <span aria-hidden="true">›</span>
              </button>
            );
            case 'actions': return <ActionCard key={it.id} result={it.result} />;
            case 'typing': return wrap(<TypingDots />);
            case 'bot': return wrap(<BotText text={it.text} />);
            case 'list': return wrap(<BotList title={it.title} items={it.items} />);
            case 'alert': return wrap(<BotAlert title={it.title} text={it.text} tone={it.tone} />);
            case 'acts': return wrap(<BotActions items={it.items} onAction={(b) => doAction(b.action)} disabled={false} />);
            case 'user': return <UserEcho key={it.id} text={it.text} />;
            case 'chips': return <Chips key={it.id} buttons={it.buttons} frozen={it.frozen} chosen={it.chosen} onPick={onPick} />;
            case 'multi': return (
              <MultiSelect key={it.id} options={INPUT_INFO} frozen={it.frozen}
                onDone={(sel) => {
                  freeze();
                  ctx.current.selected = sel;
                  push({ type: 'user', text: INPUT_INFO.filter((o) => sel.includes(o.key)).map((o) => o.label).join(', ') });
                  runNode('s3a');
                }} />
            );
            default: return null;
          }
        })}
      </div>
      <InputBar value={value} onChange={setValue} onSend={onSend} onPaste={onPaste}
        placeholder={PLACEHOLDER[mode]} disabled={busy} />
    </div>
  );
}
