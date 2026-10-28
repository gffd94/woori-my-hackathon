# 위비 레이더 — 스미싱 문자 판별 서비스

의심 문자를 붙여넣거나 공유하면 **위험 / 주의 / 안전 / 판단 보류** 중 하나로 판정하고, 판정 이유와 다음 행동을 안내하는 서비스입니다.

## 서비스 소개

### 무엇이 다른가

일반 챗봇은 문자를 AI에게 그대로 묻고 그 답을 결과로 보여줍니다. 이 서비스는 AI 판단을 그대로 믿지 않습니다.

- **DB 대조**: 신고된 악성 URL·도메인·전화번호(약 8.6만 건)와 공식 도메인 목록에 문자 속 링크·번호를 대조합니다.
- **신종 수법 검색 (RAG)**: 사칭 수법 카드와 비슷한지 글자(n-gram)와 의미(임베딩)로 함께 검색해 AI에게 참고 자료로 줍니다. 수법 카드는 보호나라 공지를 수집해 정리한 것입니다.
- **서버 규칙 판정**: AI는 위험 신호만 고르고, 최종 판정은 서버 규칙이 내립니다. 처리 중 하나라도 실패하면 안전이라고 말하지 않고 판단을 보류합니다.

### 판별 흐름

```
문자 입력
 → ① URL·도메인·전화번호 추출
 → ② 악성 단서·공식 도메인 DB 대조
 → ③ 개인정보 마스킹 (전화번호·계좌·카드·주민번호·이메일)
 → ④ 수법 카드 검색 (n-gram + pgvector, RRF로 최대 5개)
 → ⑤ LLM이 위험 신호와 근거 문구를 고름 (근거가 문자에 없으면 버림)
 → ⑥ 서버 규칙으로 최종 판정
 → ⑦ 마스킹한 판정 기록 저장 (verdict_logs)
```

### 판정 결과

| 판정 | 화면 | 기준 (요약) |
|---|---|---|
| 위험 (`RISK`/`high`) | 스미싱 위험이 의심돼요 | 악성 DB 일치, 강한 신호, 신호 2개 이상, 미확인 링크·번호와 의심 근거의 결합 |
| 주의 (`RISK`/`low`) | 일부 주의 신호가 보여요 | 약한 신호 1개, 미확인 링크·번호만 있음 |
| 안전 (`SAFE`) | 위험 징후가 발견되지 않았어요 | 위 근거가 없음. 안전을 보장한다는 뜻은 아님 |
| 판단 보류 (`UNKNOWN`) | 분석할 정보가 부족해요 | DB·검색·LLM 처리 실패, 해석할 수 없는 URL |

자세한 규칙은 [SPEC.md](SPEC.md) 2.10, 응답 형식은 [docs/API.md](docs/API.md)에 있습니다.

### 개인정보 보호

- 요청에는 문자 내용과 입력 방식(`paste`/`share`)만 담습니다. 사용자 식별 정보는 받지 않습니다.
- LLM·임베딩 API로 보내기 전, 그리고 판정 기록에 저장하기 전에 전화번호·계좌·카드·주민번호·이메일·URL의 개인 경로를 가립니다. 원문은 저장하지 않습니다.
- 오류 응답과 서버 로그에는 입력 원문과 비밀값을 남기지 않습니다.

### 성능 비교 결과

같은 AI 모델(gpt-4o-mini)로 세 방식을 비교했습니다. 검증 세트는 179건입니다(공개 데이터셋 스미싱 79건, 팀이 작성한 정상 문자 100건).

| | 일반 챗봇 방식 (LLM 단독) | LLM + DB 조회 | 이 서비스 |
|---|---|---|---|
| 스미싱 탐지율 | 100% | 100% | 95% |
| 정상 문자 오탐률 | 44% | 42% | **26%** |

놓친 스미싱 4건은 데이터셋에서 전화번호·링크가 지워진 문자입니다. 실험 방법은 아래 [성능 비교 실험](#성능-비교-실험-선택)을 참고하세요.

### 기술 스택

| 영역 | 사용 기술 |
|---|---|
| 백엔드 | Python 3.12, FastAPI, SQLAlchemy, psycopg |
| DB | PostgreSQL + pgvector (Aiven) |
| AI | OpenAI gpt-4o-mini (판단), text-embedding-3-small (1536차원 임베딩) |
| 프론트엔드 | React 18, Vite |
| 평가 | LangSmith |

### 폴더 구조

```
app/
  main.py            FastAPI 앱, CORS, 전역 오류 처리
  routers/analyze.py POST /analyze
  services/          추출·마스킹·DB 대조·검색·LLM·판정 (analyzer.py가 전체 흐름)
  commands/          수법 카드 임베딩 재색인 명령
  db/                DB 모델과 세션
frontend/            React 화면 (채팅형 판별 화면)
tests/               백엔드 테스트 (pytest)
eval/                성능 비교 실험 스크립트 (LangSmith)
docs/                API 명세, 진행 현황
SPEC.md              요구사항·설계 기준 문서
```

## 프로토타입 실행 방법

아래 명령은 Windows PowerShell 기준입니다. 저장소 최상위 폴더에서 실행합니다.

### 준비물

- Python 3.12
- Node.js 20 이상 (npm 포함)
- 팀 공용 DB 접속 주소(`DATABASE_URL`), OpenAI API 키 — 팀 담당자에게 받습니다. 공용 DB에는 악성 단서·공식 도메인·수법 카드(임베딩 포함)가 이미 들어 있습니다.

### 1. 백엔드

```powershell
# 가상환경과 패키지
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt

# 환경 변수 파일 (.env가 이미 있으면 덮어쓰지 않는다)
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
```

`.env`를 열어 아래 값을 채웁니다. `.env`는 Git에 올라가지 않습니다.

| 변수 | 값 |
|---|---|
| `DATABASE_URL` | `postgresql+psycopg://...` 형식의 공용 DB 주소 |
| `OPENAI_API_KEY` | OpenAI 키 (LLM 판단용) |
| `EMBEDDING_API_KEY` | OpenAI 키 (임베딩용, 같은 키를 넣어도 됨) |
| `FRONTEND_ORIGINS` | 프론트 주소. 기본값 `http://localhost:5173` 그대로 |

나머지 값(`OPENAI_MODEL`, `EMBEDDING_*`)은 예시 파일 값을 그대로 씁니다.

```powershell
# 서버 실행
.\.venv\Scripts\python.exe -m uvicorn app.main:app --port 8000
```

http://localhost:8000/docs 에서 API 문서를 열고 `POST /analyze`를 직접 호출해 볼 수 있습니다.

### 2. 프론트엔드

새 터미널에서 실행합니다.

```powershell
cd frontend
npm ci

# 백엔드 주소 설정 (이 파일이 없으면 가짜 응답으로 동작한다)
if (-not (Test-Path .env.local)) { Set-Content .env.local "VITE_API_BASE_URL=http://localhost:8000" }

npm run dev
```

브라우저에서 http://localhost:5173 을 엽니다.

> `VITE_API_BASE_URL`을 비워 두면 백엔드 없이 `src/api/mock.js`의 가짜 응답으로 화면만 확인할 수 있습니다.

### 3. 동작 확인

아래 문자를 채팅 입력창에 붙여넣거나, PowerShell에서 직접 호출합니다.

```powershell
$body = @{ message = "[우리은행] 정기예금 만기 안내. 자세한 내용은 https://wooribank.com 에서 확인하세요." } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri http://localhost:8000/analyze -ContentType "application/json; charset=utf-8" -Body ([Text.Encoding]::UTF8.GetBytes($body))
```

| 예시 문자 | 기대 결과 |
|---|---|
| `[우리은행] 정기예금 만기 안내. 자세한 내용은 https://wooribank.com 에서 확인하세요.` | 안전 |
| `엄마 나 폰 액정 깨져서 임시폰으로 연락해. 급하게 문상 사야 하는데 카드 사진 좀 보내줘` | 위험 |
| `[검찰청] 고객님 명의 계좌가 범죄에 연루되었습니다. 오늘 안에 본인인증 후 연락 바랍니다.` | 위험 |

판정 한 건에 3~5초가 걸립니다(임베딩과 LLM 호출 포함).

### 문제 해결

| 증상 | 원인과 해결 |
|---|---|
| 항상 `503` | DB에 연결되지 않아 판정 기록을 저장하지 못함. `DATABASE_URL`을 확인 |
| 항상 판단 보류(`UNKNOWN`) | OpenAI 키 오류, 또는 수법 카드 벡터가 비어 있음. 키를 확인하고 아래 재색인을 실행 |
| 화면에서 "일시 오류" | 백엔드가 꺼져 있거나 CORS 차단. 백엔드 실행 여부와 `FRONTEND_ORIGINS` 확인 |
| 화면 결과가 매번 비슷함 | 프론트가 가짜 응답을 쓰는 중. `frontend/.env.local`의 `VITE_API_BASE_URL` 확인 후 `npm run dev` 재시작 |

수법 카드 벡터가 비어 있을 때만 실행합니다(외부 API 비용 1원 미만).

```powershell
.\.venv\Scripts\python.exe -m app.commands.reindex_patterns --dry-run   # 대상만 확인
.\.venv\Scripts\python.exe -m app.commands.reindex_patterns             # 실제 임베딩
```

## 테스트 실행 방법

### 백엔드 테스트

DB와 외부 API는 가짜로 대체되어 있어 **키나 DB 없이** 실행됩니다.

```powershell
.\.venv\Scripts\python.exe -m pytest
```

- 전체 549개 (2026-10-28 기준)
- `tests/test_pgvector_integration.py`는 전용 테스트 DB 주소(`HARNESS_DATABASE_URL`)가 있을 때만 실행되고, 없으면 건너뜁니다.

특정 파일만 실행하려면:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_final_decision.py -q
```

### 프론트엔드 테스트

```powershell
cd frontend
node --test src/api/resultDetails.test.js src/components/EvidenceDetails.test.js
```

### 성능 비교 실험 (선택)

일반 챗봇 방식(A), DB 조회 추가(B), 이 서비스(D)를 같은 문자로 돌려 LangSmith에서 비교합니다. **OpenAI 비용(전체 약 500~700원)과 LangSmith 계정이 필요합니다.**

```powershell
.\.venv\Scripts\python.exe -m pip install -r eval/requirements.txt

# .env에 추가: LANGSMITH_API_KEY=..., LANGSMITH_PROJECT=smishing-eval

.\.venv\Scripts\python.exe -m eval.build_testset                 # 시험 세트 260건 (eval/data/, Git 제외)
.\.venv\Scripts\python.exe -m eval.build_testset --validation    # 검증 세트 179건
.\.venv\Scripts\python.exe -m eval.run_experiments --ids K-006 --experiments D   # 1건 시범 실행
.\.venv\Scripts\python.exe -m eval.run_experiments --set validation --tag v2     # 검증 세트 A·B·D
```

결과는 LangSmith의 Datasets & Experiments 화면과 `eval/data/results_*.json`에서 볼 수 있습니다. LangSmith에는 마스킹한 문자만 올라갑니다.

## 참고 문서

- [SPEC.md](SPEC.md) — 요구사항, 판정 규칙, 테스트 기준
- [docs/API.md](docs/API.md) — `POST /analyze` 요청·응답
- [docs/STATUS.md](docs/STATUS.md) — 진행 현황과 알려진 문제
- [AGENTS.md](AGENTS.md) — 작업 규칙 (브랜치, 승인, 보안)
