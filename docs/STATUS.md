# 진행 상황과 알려진 문제 (2026-10-27 기준)

이 저장소에서 작업을 시작하는 사람과 AI가 먼저 읽는 문서다. 기준 문서는 `SPEC.md`와 `AGENTS.md`이며, 이 문서는 **SPEC에 없는 최신 결정, 실제 DB 상태, 코드 진행 상황**을 알려 준다.
작업을 끝내면 이 문서의 해당 항목을 갱신한다.

## 1. 확정된 결정

SPEC 개정(PR #8)으로 ERD 구조, 신고·관리자 기능 MVP 제외, 요청 `source`(share/paste), `FRONTEND_ORIGINS`, `LLM_*`·`EMBEDDING_*` 설정 이름, `/analyze` 응답의 `retrieval`·nullable `matched_cases`·`guide_type`(damage_stage/prevention/verification)이 SPEC에 반영됐다.

SPEC이 미확정으로 남긴 항목 중 `feature/analyze-api`에서 정한 값:

| 항목 | 결정 | 비고 |
|---|---|---|
| indicators 지원 유형 | `url`, `domain`, `phone` | 실제 DB 데이터 기준 |
| 공식 근거 | `official_links.domain` 완전 일치 + https·포트/쿼리/사용자정보 없음일 때만 공식 URL로 본다. 문자의 모든 URL이 공식이어야 SAFE 후보 | 검증 정보(`verification_reference`, `verified_at`)가 NULL인 행도 현재는 인정 |
| 전화번호 | 악성 일치가 아니면 미확인. 전화번호가 있으면 SAFE가 나오지 않는다 | 공식 전화번호 데이터 없음 |
| 명확한 위험 신호 | LLM `is_high_risk=true`이고 신호 2개 이상 | 기존 규칙 유지 |
| LLM SAFE 제안 | `LLMJudgement.suggestion`(RISK/SAFE/UNKNOWN). 없으면 SAFE 제안이 아님 | 5번(llm-settings)과 공유 |
| 이유 문구 | 서버 고정 문구만 응답에 쓴다. `reason_code`는 null | 코드 목록 미확정 |
| 503 응답 | `{"detail": {"code": "VERDICT_LOG_UNAVAILABLE", "message": ...}}` | error-handling 형식을 따름 |
| verdict_logs | `score`=NULL, `model_version`=`LLM_MODEL` 설정값, 검색 미완료면 패턴 ID 빈 배열 | `model_version`은 DB에서 NOT NULL이라 설정 없을 때 값 결정 필요 |

## 2. 실제 DB 상태 (2026-10-27 읽기 전용 조회)

| 테이블 | 행 수 | 확인한 내용 |
|---|---|---|
| `sources` | (미조회) | 기존 크롤링 원본 `source`를 `sources`로 합쳤다(DB 담당자 확인). `source` 테이블은 더 이상 없다 |
| `source_classifications` | (미조회) | ERD에 없는 테이블. 용도 확인 필요 |
| `patterns` | 15 | 모두 `is_active=true`. **임베딩 생성 작업 중**(조회 시점 15건 모두 NULL). 컬럼이 차원 없는 `vector` |
| `pattern_sources` | 51 | 복합 PK, FK → `patterns`, `sources` |
| `indicators` | 86,544 | url 71,514 / domain 15,010 / phone 20. (type, value_normalized) UNIQUE. URL이 원래 형태(`http://...?=...`)로 저장돼 extractor 정규화와 일치하는지 확인 필요 |
| `official_links` | 40 | domain UNIQUE. 표본 5건은 검증 정보 NULL |
| `verdict_logs` | 0 | `score`만 NULL 허용(real). `model_version`·`reasoning` NOT NULL. ID 배열 기본값 `'{}'` |
| `alembic_version` | 없음 | 테이블을 Alembic 없이 생성 |

`patterns.example_messages`는 `[{"text", "type", "source_post_id"}]` 배열이다.

**임베딩 주의:** 질의 임베딩(`/analyze`)은 카드 임베딩과 **같은 모델·같은 텍스트 구성**이어야 비교할 수 있다. 임베딩 생성 담당자는 모델 이름과 카드 텍스트 구성 방식을 이 문서에 적는다. 벡터가 NULL인 활성 카드가 남아 있으면 검색은 limited가 되어 모든 판정이 UNKNOWN이다(SPEC 2.7.3).

## 3. 코드 현황

| 영역 | 상태 |
|---|---|
| `POST /analyze` (`app/routers/analyze.py`) | 연결됨. 단 실제 DB 대조·검색·기록 저장이 미연결이라 **실제 서버에서는 항상 503**. 테스트는 대역으로 RISK·SAFE·UNKNOWN·503 검증 |
| `app/services/analyzer.py` | 핵심 흐름 완료(mock 검증). 대조·임베딩·검색·LLM·저장을 생성자 함수로 받는다. 운영 연결은 `build_default_analyzer` |
| `app/services/decision.py` | SPEC 2.10 판정 `decide_final` 추가. 기존 `decide`·`check_blacklist`·`DecisionResult`는 기존 하네스용으로 남김 |
| `app/services/masking.py` | 전화·주민·카드·계좌번호·이메일·URL 쿼리/긴 토큰 마스킹. 이름·주소는 대상 아님 |
| `app/services/embedding.py` | OpenAI 호환 임베딩 호출·검증(1536차원, NaN·영벡터·모델명). 실제 호출은 미검증 |
| `app/services/llm_judge.py` | `suggestion` 필드 추가. 아직 `OPENAI_API_KEY`를 직접 읽고 응답 앞부분을 로그에 남긴다(5번에서 정리) |
| `app/services/retriever.py` | `entities`/`cases` 조회. **ERD 기준으로 다시 써야 한다**(묶음 B) |
| `app/services/extractor.py` | 완료 |
| `app/db/models.py` | 실제 DB와 다르다(4절). SPEC상 실제 스키마 확인·승인 전 수정 금지 |
| `app/db/session.py`, `app/config.py` | 완료 |
| `app/schemas/analyze.py` | 응답은 SPEC 2.11 반영. 요청 `source`는 `feature/error-handling`에서 추가 |
| 전역 예외 처리 | `feature/error-handling` 진행 중(미병합) |
| CORS | 미구현(`feature/cors`) |
| 신고·관리자 schema(`report.py`, `case.py`, `CaseStatus`) | MVP 제외. SPEC상 승인 없이 수정·삭제하지 않는다 |

## 4. 실제 DB와 `models.py`의 차이

- `Source`: 테이블 `sources`는 이름이 맞지만 컬럼 구성은 미확인(조회 안 함).
- `Pattern`: ERD에 없는 `risk_level`, `first_seen_at`, `last_seen_at`이 있다. `example_messages`가 text[] → 실제 jsonb. `Vector()` 차원 미지정(실제 컬럼도 미지정) → 1536으로 맞출 필요.
- `pattern_indicators` 연결 테이블: 실제 DB에 없다.
- `OfficialLink`: type, value_normalized, institution → 실제는 domain(UK), organization, category, verification_reference, verified_at.

## 5. 알려진 문제

| 문제 | 상태 |
|---|---|
| `tests/test_config.py::test_missing_optional_settings_are_none_and_declared_defaults_are_used`가 `.env`에 `DATABASE_URL`이 있는 PC에서만 실패한다. `load_dotenv()`가 작업 위치가 아니라 `config.py` 위치에서 `.env`를 찾기 때문이다. | 미수정. 이 1건 실패는 예상된 결과다. |
| `tests/test_pgvector_integration.py`는 `HARNESS_DATABASE_URL`이 있어야 실행되고 없으면 건너뛴다. 예전 `entities`/`cases` 구조만 검증한다. | retriever 재작성 때 함께 정리 |
| `tests/test_pipeline_harness.py`, `test_retriever.py`, `test_retrieval_details.py`, `test_decision.py`는 예전 구조·규칙(entities/cases, pending 등록, 공식 1건 SAFE)을 검증한다. | retriever 재작성 때 변경안 승인 후 정리 |
| `feature/error-handling`과 `feature/analyze-api`가 `app/main.py` import 부근을 같이 수정한다. | 나중에 머지되는 쪽에서 두 변경을 모두 남기면 된다 |

## 6. 다음 작업

1. `feature/error-handling` 머지 (요청 `source`, 422/500 형식)
2. `feature/cors` (`FRONTEND_ORIGINS`)
3. `feature/analyze-api` 묶음 B: retriever를 `indicators`·`official_links`·`patterns` 기준 `text()` SQL로 재작성, `verdict_logs` INSERT, 실제 DB 스모크 테스트(유료 호출 승인 필요)
   - 선행: 카드 임베딩 완료, 임베딩 모델·카드 텍스트 구성 공유, `model_version` 기본값 결정
4. `fix/llm-settings`: `LLM_*`·`EMBEDDING_*` 통일, `.env.example`, `llm_judge` 로그 정리
5. `feature/db-models`: `models.py`를 실제 DB에 맞춤 (승인 필요)
6. `docs/api-spec`: 프론트용 `docs/API.md`
7. 프론트 연결 (React + Vite)

오늘 범위에서 제외: 신고·관리자 API와 인증, 요청 제한(413/429), `/analyze/image`, 외부 URL 검사 API.

## 7. 로컬 실행 시 주의

- 터미널은 **PowerShell**을 쓴다. cmd에서는 `$env:`와 `Activate.ps1`이 "파일 이름, 디렉터리 이름 또는 볼륨 레이블 구문이 잘못되었습니다" 오류로 실패한다.
- 패키지는 `.venv`에만 설치돼 있다. 활성화 여부와 상관없이 `.\.venv\Scripts\python.exe -m pytest`, `.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload`처럼 경로를 직접 지정한다.
- `.env`는 각자 만든다(커밋 금지). `DATABASE_URL`은 `postgresql+psycopg://...` 형식이다. `postgresql://`로 쓰면 SQLAlchemy가 설치되지 않은 psycopg2를 찾는다.
- DB에는 pgvector가 설치돼 있다.
- PowerShell 파이프로 `git commit -F -`를 쓰면 커밋 메시지 앞에 BOM이 붙는다. 메시지는 UTF-8 파일로 저장해 `git commit -F <파일>`로 넘긴다.
- `/analyze` 테스트는 `tests/analyze_support.py`의 `block_real_calls`로 실제 DB·외부 HTTP 시도를 막는다. 새 API 테스트도 이 fixture를 쓴다.
