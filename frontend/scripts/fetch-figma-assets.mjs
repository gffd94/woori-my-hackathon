// Figma MCP가 발급한 에셋 URL을 public/figma/ 아래로 내려받습니다.
// 이 URL은 발급 후 7일(2026-11-03 무렵)이 지나면 만료됩니다.
// 만료됐다면 Figma에서 같은 레이어를 SVG/PNG로 내보내 아래 파일 이름으로 public/figma/에 넣어 주세요.
// 실행: npm run fetch-assets  (Node 18 이상)

import { mkdir, writeFile } from 'node:fs/promises';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = join(dirname(fileURLToPath(import.meta.url)), '..', 'public', 'figma');

const CHAT = 'https://www.figma.com/api/mcp/asset/00eb34ed-d4f7-4b84-bd53-4dc8844539f0';
const RESULT = 'https://www.figma.com/api/mcp/asset/18c7c365-174a-462e-b0de-a2c695a5bd87';
const HOME = 'https://www.figma.com/api/mcp/asset/18810af4-61f6-42f0-8d3f-2c49aa9f055c';

// [저장할 파일 이름, 원본 URL, Figma 노드]
// 카드·말풍선 같은 컨테이너 배경은 CSS(src/styles.css의 색상 토큰)로 그렸고, 여기에는 아이콘과 이미지만 있습니다.
const ASSETS = [
  // 공통 · 대화 화면 (woori_message_input 7:2511)
  ['wibee.png', `${CHAT}/68fb6.png`, '7:2528 위비 캐릭터'],
  ['chat-bg.svg', `${CHAT}/95f68.svg`, '7:2511 배경'],
  ['header-icon-bg.svg', `${CHAT}/6c5ef.svg`, '19:101'],
  ['header-shield.svg', `${CHAT}/76035.svg`, '19:102'],
  ['header-check.svg', `${CHAT}/ef5c8.svg`, '19:103'],
  ['icon-back.svg', `${CHAT}/24d42.svg`, '7:2516'],
  ['icon-close.svg', `${CHAT}/ba999.svg`, '7:2523'],
  ['avatar-circle.svg', `${CHAT}/bd050.svg`, '7:2527'],
  ['guide-badge.svg', `${CHAT}/009b4.svg`, '7:2544'],
  ['guide-shield.svg', `${CHAT}/59969.svg`, '7:2545'],
  ['guide-check.svg', `${CHAT}/427a3.svg`, '7:2546'],
  ['url-arrow.svg', `${CHAT}/915f1.svg`, '7:2557'],
  ['avatar-circle-sm.svg', `${CHAT}/45ec9.svg`, '7:2561'],
  ['dot-1.svg', `${CHAT}/644dd.svg`, '7:2565'],
  ['dot-2.svg', `${CHAT}/c4b8d.svg`, '7:2566'],
  ['dot-3.svg', `${CHAT}/5ae5a.svg`, '7:2567'],
  ['input-btn-bg.svg', `${CHAT}/6860b.svg`, '7:2583'],
  ['input-clip.svg', `${CHAT}/d4f9b.svg`, '7:2584'],
  ['input-img-frame.svg', `${CHAT}/f1a37.svg`, '7:2586'],
  ['input-img-sun.svg', `${CHAT}/b57a5.svg`, '7:2587'],
  ['input-img-hill.svg', `${CHAT}/69bd3.svg`, '7:2588'],
  ['send-bg.svg', `${CHAT}/4f8b6.svg`, '7:2590'],
  ['send-arrow.svg', `${CHAT}/2bff5.svg`, '7:2591'],

  // 결과 리포트 (woori_result_report 19:2)

  ['factor-url.png', 'https://www.figma.com/api/mcp/asset/cc41b0b7-3208-4412-92b4-5c5dd7846729/1b3d5.png', '43:18 출처 불명 URL 아이콘'],
  ['factor-urgent.png', 'https://www.figma.com/api/mcp/asset/a13a5197-aa7a-44e8-8012-20061e881ee0/984b8.png', '43:12 긴급 행동 유도 아이콘'],
  ['factor-imperson.png', 'https://www.figma.com/api/mcp/asset/8bff100e-cec9-4c12-8936-de2e6fde3c4b/ce18d.png', '43:15 사칭 아이콘'],
  ['action-icon.png', 'https://www.figma.com/api/mcp/asset/be56aa0e-414c-4b56-a8ea-3ab6a38dbec5/d49b2.png', '43:21 지금 이렇게 해주세요 아이콘'],

  // 결과 카드 위비 얼굴 (상태별 이미지)
  ['face-risk.png', 'https://www.figma.com/api/mcp/asset/8cc7379b-881c-49db-a2b6-9d7e357b3e3c/15603.png', '63:6 위험 (봄봄)'],
  ['face-safe.png', 'https://www.figma.com/api/mcp/asset/afe34b34-15e9-477b-9771-226d56fc1a57/9fb93.png', '63:2 위험 징후 없음 (푸딩)'],
  ['face-caution.png', 'https://www.figma.com/api/mcp/asset/ea738557-f06d-4472-ad50-c1b101bfd67a/f888d.png', '63:4 낮은 위험 (달보)'],
  ['face-nodata.png', 'https://www.figma.com/api/mcp/asset/40cc681d-0e1b-4d1f-ad6b-870137ff439e/ee334.png', '75:122 정보 부족 (큐)'],

  // 홈 (woori home 17:4)
  ['home-bg.svg', `${HOME}/987d4.svg`, '17:4 배경'],
  ['home-icon.png', `${HOME}/103f6.png`, '40:3'],
  ['home-close.svg', `${HOME}/373c4.svg`, '17:10'],
  ['page-dot.svg', `${HOME}/1a491.svg`, '17:6'],
  ['page-dot-active.svg', `${HOME}/ccc74.svg`, '17:7'],
  ['smile.svg', `${HOME}/ebb63.svg`, '19:146'],
  // 예금·적금 타일 (이전 홈 프레임 7:2310에서 가져옴)
  ['tile-deposit-a.svg', 'https://www.figma.com/api/mcp/asset/6c902e62-325f-47b3-9ea3-a81f1ce75e37/a6abd.svg', '7:2342'],
  ['tile-deposit-b.svg', 'https://www.figma.com/api/mcp/asset/4b890b94-65f3-4ef8-8c6c-c3aeacdd9f26/f8823.svg', '7:2343'],
  ['tile-deposit-c.svg', 'https://www.figma.com/api/mcp/asset/955803fb-7781-425b-802f-501c744d6452/c9961.svg', '7:2344'],
  ['tile-loan.svg', `${HOME}/f8ed5.svg`, '17:37'],
  ['tile-won-a.svg', `${HOME}/e7ccd.svg`, '17:38'],
  ['tile-won-b.svg', `${HOME}/523e9.svg`, '17:39'],
  ['tile-fx-a.svg', `${HOME}/39684.svg`, '17:41'],
  ['tile-fx-b.svg', `${HOME}/8454e.svg`, '17:42'],
  ['tile-pension-a.svg', `${HOME}/437ec.svg`, '17:43'],
  ['tile-pension-b.svg', `${HOME}/6d327.svg`, '17:44'],
  ['tile-smishing.png', `${HOME}/d17bd.png`, '17:107'],
  ['home-divider.svg', `${HOME}/5da1c.svg`, '17:100'],
  ['home-input-grid.svg', `${HOME}/9d912.svg`, '17:56'],
  ['home-send-bg.svg', `${HOME}/d846f.svg`, '17:62'],
  ['ground-a.svg', `${HOME}/f5dcc.svg`, '17:65'],
  ['ground-b.svg', `${HOME}/18d25.svg`, '17:66'],
  ['grass.svg', `${HOME}/ca9b6.svg`, '17:67'],
  ['flower-petal.svg', `${HOME}/7161c.svg`, '17:75'],
  ['flower-side.svg', `${HOME}/c701c.svg`, '17:76'],
  ['flower-center.svg', `${HOME}/fb3fb.svg`, '17:78'],
  ['char-1.png', `${HOME}/144ad.png`, '17:69'],
  ['char-3.png', `${HOME}/a72db.png`, '17:71'],
  ['char-4.png', `${HOME}/3ac5f.png`, '17:72'],
  ['char-5.png', `${HOME}/f79e0.png`, '17:73'],
  ['char-6.png', `${HOME}/c6e63.png`, '17:74'],
];

await mkdir(root, { recursive: true });
let ok = 0;
for (const [name, url, node] of ASSETS) {
  try {
    const res = await fetch(url);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const buf = Buffer.from(await res.arrayBuffer());
    if (!buf.length) throw new Error('empty file');
    await writeFile(join(root, name), buf);
    ok++;
  } catch (err) {
    console.error(`실패 ${name} (${node}): ${err.message}`);
  }
}
console.log(`${ok}/${ASSETS.length}개 에셋 저장 → public/figma/`);
