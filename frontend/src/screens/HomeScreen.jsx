import { useEffect, useRef, useState } from 'react';
import Ico from '../components/Ico.jsx';
import { fig } from '../assets.js';

// 우리WON뱅킹 챗봇 홈 (Figma woori home 17:4). 안심톡 진입점은 '스미싱 확인' 타일입니다.

// 하단 캐릭터 일러스트 좌표 (Figma 17:64, 그룹 상단 y=681 기준)
const CHARS = [
  ['char-1.png', 18.36, 19.11, 73.46, 88.17],
  ['wibee.png', 68.74, 0, 83.17, 107.28],
  ['char-3.png', 141.59, 28.36, 55.85, 78.92],
  ['char-4.png', 178.62, 16.03, 72.24, 90.02],
  ['char-5.png', 230.83, 13.56, 67.39, 92.49],
  ['char-6.png', 290.33, 9.87, 72.85, 96.19],
];
const FLOWERS = [
  [28.07, 98.04, 26.25, 100.5, 33.53, 100.5, 30.5, 100.5],
  [100.92, 96.19, 99.1, 98.65, 106.38, 98.65, 103.35, 98.65],
  [152.52, 99.27, 150.7, 101.74, 157.98, 102.97, 154.95, 101.74],
  [204.12, 96.8, 202.3, 99.27, 209.59, 99.27, 206.55, 99.27],
  [343.75, 98.65, 341.93, 101.12, 349.21, 101.12, 346.18, 101.12],
];

export default function HomeScreen({ onOpenSafeTalk, onToast }) {
  return (
    <div className="screen home">
      <div className="home__top">
        <span className="home__dots" aria-hidden="true">
          <Ico name="page-dot.svg" w={6} h={6} />
          <Ico name="page-dot-active.svg" w={16} h={8} />
          <Ico name="page-dot.svg" w={6} h={6} />
        </span>
        <button className="home__restart" onClick={() => onToast('처음 화면이에요.')}>
          <img className="home__restart-icon" src={fig('home-icon.png')} alt="" />
          처음으로
          <Ico name="home-close.svg" w={12} h={12} inset="-7.5%" />
        </button>
      </div>
      <p className="home__date">2026.10.27</p>

      <section className="home-card home-card--update">
        <p className="home-card__eyebrow">우리WON뱅킹(앱)</p>
        <p className="home-card__headline">업데이트 안내</p>
        <button className="home-card__more" onClick={() => onToast('업데이트 안내 화면으로 이동해요.')}>알아보기 ›</button>
        <img className="home-card__wibee" src={fig('wibee.png')} alt="" />
      </section>

      <section className="home-card home-card--greet">
        <p className="home-card__hello">고객님, 좋은 아침이에요!</p>
        <p className="home-card__line">은행 업무에 대해 궁금한 점이 있으시다면</p>
        <p className="home-card__line">저 <b>AI챗봇</b>에게 말씀해주세요.
          <Ico name="smile.svg" w={14} h={14} className="home-card__smile" />
        </p>
      </section>

      <TileScroller onOpenSafeTalk={onOpenSafeTalk} onToast={onToast} />

      <div className="friends" aria-hidden="true">
        <Ico name="ground-a.svg" w={394.6} h={31.14} className="abs" style={{ left: 5, top: 86.63 }} />
        <Ico name="ground-b.svg" w={394.6} h={20.67} className="abs" style={{ left: 5, top: 98.33 }} />
        <Ico name="grass.svg" w={12.14} h={11.1} inset="-9.01% -8.24%" className="abs" style={{ left: 12.29, top: 95.57 }} />
        <Ico name="grass.svg" w={12.14} h={11.1} inset="-9.01% -8.24%" className="abs" style={{ left: 370.46, top: 93.72 }} />
        {CHARS.map(([n, x, y, w, h]) => (
          <img key={n} src={fig(n)} alt="" className="friends__char" style={{ left: x, top: y, width: w, height: h }} />
        ))}
        {FLOWERS.map((f, i) => (
          <span key={i}>
            <Ico name="flower-petal.svg" w={8.5} h={8.63} className="abs" style={{ left: f[0], top: f[1] }} />
            <Ico name="flower-side.svg" w={4.86} h={4.93} className="abs" style={{ left: f[2], top: f[3] }} />
            <Ico name="flower-side.svg" w={4.86} h={4.93} className="abs" style={{ left: f[4], top: f[5] }} />
            <Ico name="flower-center.svg" w={3.64} h={3.7} className="abs" style={{ left: f[6], top: f[7] }} />
          </span>
        ))}
      </div>

      <div className="home-input">
        <div className="home-input__field">
          <Ico name="home-input-grid.svg" w={16} h={16} />
          <span className="home-input__ph">문의하실 내용을 입력해주세요.</span>
          <button className="home-input__send" aria-label="보내기" onClick={() => onToast('일반 상담 챗봇은 이 데모 범위 밖이에요.')}>
            <Ico name="home-send-bg.svg" w={24} h={24} />
            <Ico name="send-arrow.svg" w={12} h={14} inset="-6.43% -7.5%" className="abs" style={{ left: 6, top: 5 }} />
          </button>
        </div>
      </div>
    </div>
  );
}

// 바로가기 타일: 가로 스크롤 + 아래 막대(17:100)를 스크롤 위치 표시줄로 사용
function TileScroller({ onOpenSafeTalk, onToast }) {
  const ref = useRef(null);
  const drag = useRef(null);
  const [thumb, setThumb] = useState({ left: 0, width: 1 });

  const update = () => {
    const el = ref.current;
    if (!el) return;
    const ratio = el.clientWidth / el.scrollWidth;
    const max = el.scrollWidth - el.clientWidth;
    const width = Math.min(1, ratio);
    setThumb({ width, left: max > 0 ? (el.scrollLeft / max) * (1 - width) : 0 });
  };

  useEffect(() => {
    update();
    window.addEventListener('resize', update);
    return () => window.removeEventListener('resize', update);
  }, []);

  // 데스크톱 시연용 마우스 드래그 스크롤 (터치는 기본 스크롤 사용)
  const onPointerDown = (e) => {
    if (e.pointerType !== 'mouse') return;
    drag.current = { x: e.clientX, left: ref.current.scrollLeft, moved: false };
  };
  const onPointerMove = (e) => {
    if (!drag.current) return;
    const dx = e.clientX - drag.current.x;
    if (Math.abs(dx) > 3) drag.current.moved = true;
    ref.current.scrollLeft = drag.current.left - dx;
  };
  const endDrag = () => { setTimeout(() => { drag.current = null; }, 0); };
  const guard = (fn) => () => { if (!drag.current?.moved) fn(); };

  return (
    <>
      <nav className="tiles" aria-label="바로가기" ref={ref} onScroll={update}
        onPointerDown={onPointerDown} onPointerMove={onPointerMove} onPointerUp={endDrag} onPointerLeave={endDrag}>
        <button className="tile-h" onClick={guard(() => onToast('예금·적금 메뉴로 이동해요.'))}>
          <Ico name="tile-deposit-b.svg" w={24} h={16} className="abs" style={{ left: 21, top: 14.5 }} />
          <Ico name="tile-deposit-a.svg" w={24} h={8} className="abs" style={{ left: 21, top: 18 }} />
          <Ico name="tile-deposit-c.svg" w={24} h={7.5} inset="-8.67% -2.71%" className="abs" style={{ left: 21, top: 22 }} />
          <span className="tile-h__label" style={{ top: 41 }}>예금<br />적금</span>
        </button>
        <button className="tile-h" onClick={guard(() => onToast('대출 메뉴로 이동해요.'))}>
          <Ico name="tile-loan.svg" w={40} h={30} inset="-4.17% -3.13%" className="abs" style={{ left: 13, top: 11 }} />
          <span className="tile-h__label" style={{ top: 53 }}>대출</span>
        </button>
        <button className="tile-h" onClick={guard(() => onToast('WON뱅킹 메뉴로 이동해요.'))}>
          <Ico name="tile-won-a.svg" w={16} h={16} className="abs" style={{ left: 22, top: 14 }} />
          <Ico name="tile-won-b.svg" w={16} h={16} className="abs" style={{ left: 30, top: 14 }} />
          <span className="tile-h__won" style={{ left: 24, top: 31 }}>WON</span>
          <span className="tile-h__label" style={{ top: 43 }}>WON<br />뱅킹</span>
        </button>
        <button className="tile-h tile-h--wide" onClick={guard(onOpenSafeTalk)}>
          <img className="tile-h__img" src={fig('tile-smishing.png')} alt="" draggable="false" />
          <span className="tile-h__label" style={{ top: 44 }}>스미싱<br />확인</span>
        </button>
        <button className="tile-h" onClick={guard(() => onToast('퇴직연금 메뉴로 이동해요.'))}>
          <Ico name="tile-pension-a.svg" w={28} h={21} inset="-5.95% -4.46%" className="abs" style={{ left: 19, top: 16 }} />
          <Ico name="tile-pension-b.svg" w={12} h={7} inset="-17.86% -10.42%" className="abs" style={{ left: 27, top: 8 }} />
          <span className="tile-h__label" style={{ top: 43 }}>퇴직<br />연금</span>
        </button>
        <button className="tile-h" onClick={guard(() => onToast('환전·환율 메뉴로 이동해요.'))}>
          <Ico name="tile-fx-a.svg" w={25} h={26} className="abs" style={{ left: 17, top: 11 }} />
          <Ico name="tile-fx-b.svg" w={13} h={15} inset="-8.33% -9.62%" className="abs" style={{ left: 29, top: 11 }} />
          <span className="tile-h__label" style={{ top: 42 }}>환전<br />환율</span>
        </button>
      </nav>
      <div className="tiles-bar" aria-hidden="true">
        <Ico name="home-divider.svg" w={336} h={3} />
        <span className="tiles-bar__thumb" style={{ left: `${thumb.left * 100}%`, width: `${thumb.width * 100}%` }} />
      </div>
    </>
  );
}
