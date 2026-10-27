# 우리WON 안심톡 프론트엔드

Figma 파일 `우리won 안심톡`의 모바일 화면 3개를 React로 옮기고, 설계서의 챗봇 대화 플로우와 API(`POST /analyze`, `POST /reports`)를 연결한 코드입니다.

## 실행

```bash
npm install
npm run fetch-assets   # Figma 아이콘·캐릭터 이미지를 public/figma/로 내려받기
cp .env.example .env   # 백엔드가 있으면 VITE_API_BASE_URL 입력, 없으면 비워두기(가짜 응답)
npm run dev
```

- 홈에서 **스미싱 확인** 타일을 누르면 안심톡 대화 화면으로 들어갑니다.
- 공유하기 진입은 `http://localhost:5173/?shared=문자내용` 으로 확인할 수 있습니다. 실제 앱에서는 우리WON뱅킹이 문자 앱의 공유 내용을 받아 이 주소로 WebView를 엽니다.
- 백엔드 없이 볼 때는 주소 끝에 `?sample=known`(기존 피싱) · `newRisk`(신규 피싱) · `safe`(위험 징후 없음) · `caution`(낮은 위험) · `noData`(정보 부족)를 붙이면 해당 결과 화면으로 바로 들어갑니다. 문자에 `[오류]`를 넣으면 분석 오류 화면이 나옵니다.
- 붙여넣거나 공유한 문자는 화면에 표시하고 분석하기 전에 `src/utils/mask.js`로 개인정보(주민등록번호·카드번호·계좌번호·인증번호·고객 이름)를 자동으로 가립니다. URL과 문자 속 연락처는 판정 근거라서 남깁니다.

### 에셋 주의

`npm run fetch-assets`가 쓰는 Figma 에셋 주소는 **발급 후 7일(2026-11-03 무렵)** 이 지나면 만료됩니다. 그 전에 한 번 받아서 `public/figma/`를 저장소에 커밋해 두세요. 만료됐다면 Figma에서 같은 레이어를 SVG/PNG로 내보내 `scripts/fetch-figma-assets.mjs`에 적힌 파일 이름으로 넣으면 됩니다(파일마다 Figma 노드 ID가 적혀 있습니다).

## Figma ↔ 코드 대응

| Figma 프레임 | 노드 | 코드 |
| --- | --- | --- |
| woori home | 17:4 | `src/screens/HomeScreen.jsx` |
| woori_message_input | 7:2511 | `src/screens/ChatScreen.jsx`, `src/components/Messages.jsx`, `ChatHeader.jsx`, `InputBar.jsx` |
| woori_result_report · woori_result_safe · woori_result_low_risk · woori_result_no_data | 19:2 · 54:2 · 54:108 · 75:2 | `src/components/ResultReport.jsx` |

- 좌표·글자 크기·글자색은 Figma 값 그대로이고, 절대 위치는 flex 레이아웃으로 바꿨습니다.
- 카드·말풍선 배경과 테두리 색은 Figma SVG를 직접 받지 못해 화면 캡처 기준으로 맞췄습니다. `src/styles.css` 상단 `--c-*` 토큰만 고치면 전체에 반영됩니다.
- Figma에는 결과 화면이 RISK만 있어서 SAFE·UNKNOWN 결과와 피해 단계 대화(설계서 플로우)는 같은 컴포넌트 구조에 색과 문구만 바꿔 확장했습니다.

## 구조

```
src/
├── api/
│   ├── client.js     # POST /analyze, POST /reports (VITE_API_BASE_URL 없으면 mock 사용)
│   └── mock.js       # 백엔드 없이 화면 확인용 가짜 판정 + 예시 문자
├── flow/
│   └── dialogue.js   # 설계서 '챗봇 대화 플로우'의 노드·버튼·입력 검증
├── bridge.js         # 우리WON뱅킹 앱 연결 지점 (지급정지·전화·화면 이동, 공유 진입)
├── components/       # Figma 레이어 단위 컴포넌트
├── screens/          # 홈, 안심톡 대화
└── styles.css        # Figma 수치 + 색상 토큰
```

## API 응답 형식

`/analyze` 응답은 설계서 명세를 따르되, 결과 화면의 위험 신호 목록(제목 + 설명 + 아이콘)을 그리기 위해 `reasons`를 객체로 받는 걸 권장합니다. 문자열 배열이 와도 제목만 보여주도록 처리해 두었습니다.

```json
{
  "status": "RISK",   // RISK | SAFE | CAUTION | NO_DATA
  "risk_level": "high",
  "basis": "entities",
  "matched_cases": 3,
  "guide_type": "damage_stage",
  "reasons": [
    { "code": "url", "title": "출처 불명 URL", "detail": "공식 기관 도메인인지 확인되지 않음" }
  ]
}
```

`code`는 `url` · `urgency` · `impersonation` · `other` 중 하나이며, 앞의 세 개는 Figma 아이콘과 연결됩니다.

## 앱 연결 (bridge.js)

지급정지 신청, 비밀번호 변경, 카드 분실신고, 전화 연결은 우리WON뱅킹 기존 기능이라 이 코드에서는 `window.WooriBridge.run(action)`으로 넘깁니다. 브리지가 없는 브라우저에서는 안내 토스트만 띄웁니다.
