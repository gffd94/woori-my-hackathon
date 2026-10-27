# 진행 상황과 알려진 문제 (2026-10-27 기준)

이 저장소에서 작업을 시작하는 사람과 AI가 먼저 읽는 문서다. 기준 문서는 여전히 `SPEC.md`와 `AGENTS.md`이며, 이 문서는 **SPEC과 실제 결정·코드가 어긋난 지점**을 알려 준다.
작업을 끝내면 이 문서의 해당 항목을 갱신한다.

## 1. 확정된 결정

| 항목 | 결정 | 근거 |
|---|---|---|
| DB 구조 | **ERD의 수법 카드 구조**를 쓴다. SPEC 2.5의 `entities`/`cases`는 쓰지 않는다. | 팀 ERD (아래 2절) |
| 신고·관리자 기능 | **MVP에서 제외.** `POST /reports`, `/admin/*`, 관리자 인증, 관리자 화면을 만들지 않는다. | 일정 |
| API 계약 | `/analyze`는 SPEC 2.11을 따른다. `message`는 공백만 금지·최대 5,000자, 정의되지 않은 필드는 422. | 회의 |
| `/analyze`의 `source` | 선택 필드 `share`/`paste`, 기본 `paste`. 판별 결과에 영향 없음. | 회의 (SPEC 미반영) |
| 벡터 차원 | 1536 (`Vector(1536)` 명시) | SPEC 2.8.1 |
| 환경 변수 | `LLM_*`, `EMBEDDING_*`로 통일. `OPENAI_*`는 없앤다. | SPEC 2.3, 회의 |
| Enum 위치 | `app/domain/enums.py` | 회의 |
| 프론트 | `my-hackathon/frontend`에 React + Vite(`localhost:5173`). 백엔드와 따로 띄운다. CORS 허용 주소는 `FRONTEND_ORIGINS`로 받는다. | 회의 (SPEC 미반영) |
| 브랜치 | main을 개발 통합 브랜치로 쓴다. 기능마다 `feature/*`, `fix/*`, `docs/*` 브랜치 → main PR. 머지는 사람이 한다. | 팀 |

**SPEC 개정 대기:** 위 표의 ERD 구조, 신고·관리자 제외, `source`, `FRONTEND_ORIGINS`는 아직 SPEC에 반영되지 않았다. AGENTS.md 규칙상 SPEC은 승인 후 수정한다. SPEC과 이 표가 다르면 이 표가 최신 결정이다.

## 2. ERD (확정)

```
source (크롤링 원본)  ── pattern_sources ──  patterns (수법 카드)
indicators (악성 URL·도메인 등)
official_links (공식 도메인)
verdict_logs (판정 기록)
```

| 테이블 | 컬럼 |
|---|---|
| `source` | id, site, post_id, keyword, title, posted_date, url, image_count, attachments(jsonb), collected_at, ocr_text, body_text |
| `patterns` | id, name, summary, impersonation, lure_action, triggers(text[]), example_messages(jsonb), embedding(vector), is_active |
| `pattern_sources` | pattern_id(PK·FK), source_id(PK·FK) |
| `indicators` | id, type(domain·url 등), value_normalized |
| `official_links` | id, domain(UK), organization, category, verification_reference(NULL 허용), verified_at(NULL 허용) |
| `verdict_logs` | id, message_masked, verdict(RISK·SAFE·UNKNOWN), score, matched_pattern_ids(bigint[]), matched_indicator_ids(bigint[]), reasoning, model_version, created_at |

- 데이터 흐름: 크롤링 → `source` → LLM 구조화 → `patterns` → `/analyze`가 `indicators`·`official_links` 대조와 `patterns` 유사도 검색 후 LLM 판단 → `verdict_logs` 기록.
- **실제 DB에 `source` 테이블이 이미 있다(크롤링 데이터 20건).** ERD 그림에는 `SOURCES`로 적혀 있지만 실제 이름은 `source`다. Alembic이 이 테이블을 다시 만들거나 지우지 않게 한다.

## 3. 코드 현황

| 영역 | 상태 |
|---|---|
| `app/services/extractor.py` | 완료 (URL·도메인·번호·기관명 추출) |
| `app/services/llm_judge.py` | 동작함. 단, `OPENAI_API_KEY`를 직접 읽고 URL·timeout 30초가 고정돼 있어 `Settings`를 쓰지 않는다. |
| `app/services/decision.py` | 동작함. SAFE 조건과 우선순위, `guide_type`(`none`/`verify_first`)이 SPEC 2.10(`prevention`/`verification`)과 다르다. |
| `app/services/retriever.py` | `entities`/`cases`를 조회한다. **ERD 테이블로 다시 써야 한다.** |
| `app/db/models.py` | 7개 테이블이 있지만 ERD와 컬럼이 다르다(4절). Alembic은 아직 없다. |
| `app/db/session.py` | 완료. `load_settings()`로 `.env`의 `DATABASE_URL`을 읽는다. |
| `app/config.py` | 완료. SPEC 2.3의 설정을 읽는다. |
| `app/schemas/analyze.py` | SPEC 2.11 반영. `source` 필드는 아직 없다. |
| `app/schemas/report.py`, `case.py`, `app/domain/enums.py`의 `CaseStatus` | 신고·관리자 제외 결정 전에 만든 것. **정리 대상.** |
| `app/routers/analyze.py`, `admin.py` | 빈 파일. `main.py`에 라우터 연결이 없어 `GET /`만 있다. |
| 전역 예외 처리, CORS | 없다. FastAPI 기본 422 응답은 입력 원문(`input`)을 담아 SPEC 2.11·A-04를 어긴다. |

## 4. ERD와 `models.py`의 차이

`models.py`를 ERD에 맞출 때 확인할 것이다. 의도가 불분명한 항목은 DB 담당자에게 확인한다.

- `Source`: 컬럼 4개(title, url, published_at) → ERD 12개. 테이블 이름 `sources` → 실제 `source`.
- `Pattern`: ERD에 없는 `risk_level`, `first_seen_at`, `last_seen_at`이 있다. `example_messages`가 text[] → ERD는 jsonb. `Vector()` 차원 미지정 → 1536.
- `pattern_indicators` 연결 테이블: ERD에 없다(의도 확인 필요).
- `OfficialLink`: type, value_normalized, institution → ERD는 domain(UK), organization, category.

## 5. 알려진 문제

| 문제 | 상태 |
|---|---|
| `tests/test_config.py::test_missing_optional_settings_are_none_and_declared_defaults_are_used`가 `.env`에 `DATABASE_URL`이 있는 PC에서만 실패한다. `load_dotenv()`가 작업 위치가 아니라 `config.py` 위치에서 `.env`를 찾기 때문이다. | 미수정. 이 1건 실패는 예상된 결과다. |
| `tests/test_pgvector_integration.py`는 `HARNESS_DATABASE_URL`이 있어야 실행되고, 없으면 건너뛴다. SPEC은 `TEST_DATABASE_URL`이라고 적고 있다. | 공용 DB로 수동 실행해 통과 확인함 |

## 6. 다음 작업 (순서)

1. `docs/spec-erd`: SPEC 개정 (1절의 미반영 결정)
2. `feature/error-handling`: 전역 예외 처리 (오류 형식 통일, 422에서 원문 제거, 500 일반화) + `source` 필드 + 신고·관리자 schema 정리
3. `feature/cors`: `FRONTEND_ORIGINS`
4. `feature/db-models`: `models.py`를 ERD에 맞춤, Alembic, 테이블 생성 (`source` 보존)
5. `feature/dummy-data`: 가상 수법 카드·악성 단서·공식 도메인 적재 (`is_active=true`)
6. `fix/llm-settings`: `LLM_*`·`EMBEDDING_*` 통일, `.env.example` 갱신
7. `feature/analyze-api`: retriever를 ERD에 맞추고, decision SAFE·`guide_type`을 수정하고, `POST /analyze` 연결, `verdict_logs` 기록
8. `docs/api-spec`: 프론트용 `docs/API.md`

오늘 범위에서 제외: 신고·관리자 API와 인증, 요청 제한(413/429), `/analyze/image`, 외부 URL 검사 API.

## 7. 로컬 실행 시 주의

- 터미널은 **PowerShell**을 쓴다. cmd에서는 `$env:`와 `Activate.ps1`이 "파일 이름, 디렉터리 이름 또는 볼륨 레이블 구문이 잘못되었습니다" 오류로 실패한다.
- 패키지는 `.venv`에만 설치돼 있다. 활성화 여부와 상관없이 `.\.venv\Scripts\python.exe -m pytest`, `.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload`처럼 경로를 직접 지정한다.
- `.env`는 각자 만든다(커밋 금지). `DATABASE_URL`은 `postgresql+psycopg://...` 형식이다. `postgresql://`로 쓰면 SQLAlchemy가 설치되지 않은 psycopg2를 찾는다.
- DB에는 pgvector 0.8.7이 이미 설치돼 있다.
- PowerShell 파이프로 `git commit -F -`를 쓰면 커밋 메시지 앞에 BOM이 붙는다. 메시지는 UTF-8 파일로 저장해 `git commit -F <파일>`로 넘긴다.
