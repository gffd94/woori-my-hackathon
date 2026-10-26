# 스미싱 서비스 검증 하네스

이 문서는 실행 방법과 검증 범위를 설명한다. 승인된 요구사항 SPEC을 대체하지 않는다.
현재 서비스 설계서의 추출·조회·판정 조건을 기준으로 한다.

## 기본 실행

프로젝트 폴더 `my-hackathon`에서 실행한다.

```powershell
python -m pytest -q
```

연결 시나리오의 이름과 결과를 상세히 보려면:

```powershell
python -m pytest tests/test_pipeline_harness.py -v
```

API 키·인터넷·Docker 없이 실행한다. LLM 호출은 입력에 맞춰 정해 둔 JSON이나
오류를 반환하는 테스트 함수로 대체한다. 비용이 발생하지 않으며 URL에 접속하지 않는다.
데이터는 가상 기관명·예시 도메인·메모리 DB만 사용한다.

## 조건별 검증 범위

| 조건 | 기대 결과 | 검증 파일 |
|---|---|---|
| URL·번호·기관명 추출 | 중복 제거, 도메인 소문자화, 번호 구분자 제거 | test_extractor.py |
| URL 경로의 대소문자·숫자 | 경로 보존, URL 속 숫자를 연락처로 추출하지 않음 | test_extractor.py |
| 한글에 붙은 연락처 | 번호 추출, 영문 식별자 내부 숫자는 제외 | test_service_conditions.py |
| URL의 괄호·사용자 정보·잘못된 포트 | 정상 괄호 보존, 실제 호스트 사용, 파싱 오류 격리 | test_service_conditions.py |
| 기관명 | 호출자가 제공한 목록만 추출, DB 조회 대상으로 사용하지 않음 | test_service_conditions.py |
| 공식 도메인 위장 | 부분 문자열로 공식 판정하지 않음 | test_pipeline_harness.py |
| 값은 같고 유형이 다른 DB 행 | 일치에서 제외 | test_retriever.py |
| scam 일치 | 검색과 LLM을 건너뛰고 RISK | test_pipeline_harness.py |
| 공식 정보와 위험 신호 없음 | SAFE | test_pipeline_harness.py |
| 신규 사칭·복합 위험 신호 | RISK, pending 등록 대상 표시 | test_pipeline_harness.py |
| 개인 번호만 있는 근거 부족 문자 | UNKNOWN | test_pipeline_harness.py |
| 공식 주소가 있어도 고위험 신호 존재 | RISK | test_pipeline_harness.py |
| DB·LLM 오류, LLM JSON 오류 | SAFE가 아닌 UNKNOWN | test_pipeline_harness.py |
| 사례 상태 | verified만 전달, pending/rejected 제외 | test_pipeline_harness.py |
| 벡터 검색 | 가까운 순서, limit, 영벡터/NULL 제외, 빈 결과 | test_pipeline_harness.py |
| 잘못된 벡터·limit | DB 실행 전에 ValueError | test_retriever.py, test_service_conditions.py |
| 실제 pgvector SQL | 캐스팅·연산자·정렬·상태 필터 실행 | test_pgvector_integration.py |

## 서비스 연결 계약

1. `extract(message, organization_names)`로 `ExtractedEntities`를 만든다.
2. `lookup_entities(db, extracted)`로 기존 `decision.EntityMatch` 목록을 받는다.
3. `check_blacklist(matches)`가 결과를 반환하면 이후 검색·LLM을 생략한다.
4. 같은 모델로 생성한 1536차원 임베딩을 `search_similar_cases(db, embedding)`에 전달한다.
5. `build_entity_lookup(extracted, matches)`와 사례 목록을 `judge`에 전달한다.
6. `decide(matches, judgement, matched_cases=len(cases))`로 최종 판정한다.

DB/임베딩 오류를 빈 검색 결과로 바꾸지 않는다. 운영 라우터에서는 예외 처리와
세션 롤백을 담당하고 UNKNOWN 응답으로 연결해야 한다. 블랙리스트 확인이 끝난 뒤의
LLM 오류는 기존 judge/decide가 처리한다. 테스트의 `run_pipeline`은 이 순서를 검증하는
테스트 코드이며 실제 `/analyze` 라우터를 구현한 것은 아니다.

현재 기관명은 별도 추출 결과다. judge가 원문을 받으므로 기관명도 원문으로 전달되지만,
기관명 목록을 별도 인자로 받는 기능이나 DB 유형 추가는 하지 않았다.

## 실제 PostgreSQL 검증

DB 담당자가 PostgreSQL 드라이버와 pgvector 확장이 설치된 전용 테스트 DB를 준비한 뒤,
환경 변수 `HARNESS_DATABASE_URL`에 SQLAlchemy 접속 주소를 설정한다.
PowerShell에서 주소를 이미 설정했다면 다음을 실행한다.

```powershell
python -m pytest tests/test_pgvector_integration.py -v
```

주소가 없으면 이 테스트는 SKIPPED다. 주소가 있는데 연결·드라이버·확장·SQL 오류가 발생하면
실패로 보고한다. 접속 문자열을 저장소에 기록하지 않는다.
테스트는 현재 연결에 임시 테이블을 만들고 마지막에 롤백한다. 영구 테이블·확장을 변경하지 않는다.

## 아직 증명하지 않은 것

### 상세 조회·정규화 보완

- `extractor.normalize_url/normalize_domain/normalize_phone`을 DB 적재에도 공통 사용한다.
  URL 기본 포트와 루트 슬래시는 통일하고, 경로·쿼리·fragment는 보존한다.
  기존 DB 값은 자동 변환하지 않으므로 DB 담당자가 정규화 후 중복을 검토해야 한다.
- 쿼리·fragment가 있으면 끝 구두점을 값으로 보존한다. 그 뒤 붙은 문장 구두점은
  자동으로 구분하지 못하므로 입력 화면에서 링크와 설명을 공백으로 구분한다.
- 추출 실패 URL은 `unparsed_urls`, 안내는 `warnings`에 남는다.
  `lookup_entities`, `lookup_entity_details`는 실패 URL이 있어도 scam을 먼저 조회한다.
  scam이 있으면 그 근거만 반환하고, 없으면 `ExtractionIncompleteError`를 발생시킨다.
  `build_entity_lookup`은 불완전 추출 시 계속 예외를 발생시키므로, 조회 직후
  `check_blacklist`로 RISK 여부를 먼저 확인한다. 운영 라우터에서 이 예외를 UNKNOWN으로
  변환해야 한다. 하네스는 이 동작을 검증하지만 운영 라우터는 별도로 연결해야 한다.
- `lookup_entity_details`는 source 컬럼을 읽고 `EntityDetail.as_match()`로 기존 판정에 연결한다.
- `search_case_details`는 id·message_text·distance를 반환한다. `max_distance`는 선택값이며
  검증 데이터로 정한 값을 전달한다. 임의의 기본 임계값은 적용하지 않는다.
  예를 들어 `cases = search_case_details(db, embedding, max_distance=팀에서_정한_값)`으로
  조회하고 `[case.message_text for case in cases]`를 LLM에 전달한다.
- 기존 `search_similar_cases`는 문구 목록을 반환하는 계약을 유지한다. 임계값 없는 후보 수를
  실제 유사 사례 확정 건수로 해석하지 않는다. 상세 조회의 필터 통과 건수를 사용할 수 있다.
- 임베딩 모델·전처리 일치는 호출자와 DB 적재 담당자의 계약이다. 이 두 파일이 자동 확인하지 않는다.

- 모의 LLM 테스트는 실제 모델의 탐지 정확도·프롬프트 주입 방어를 증명하지 않는다.
- 모의 벡터는 임베딩 API나 모델 품질을 증명하지 않는다. 저장·조회 임베딩 모델은 같아야 한다.
- 기본 실행의 SQLite 벡터 어댑터는 실제 PostgreSQL 연산자의 동작을 증명하지 않는다.
- 유사도 기준이 미정이므로 상위 3개를 참고 근거로 전달한다. 관련 없는 사례도 포함될 수 있다.
- `register_as_pending`은 등록 대상 표시다. 개인정보 마스킹과 실제 INSERT는 별도 담당이다.
- 실제 DB 세션·라우터 연결, 신고/관리자 API, 이미지 판별은 이번 구현 범위 밖이다.
- 프로토콜 없는 일반 도메인, 난독화 주소(hxxp, [.] 등), 국제 전화번호는 현재 추출 범위 밖이다.
- URL 뒤에 공백 없이 붙은 자연어와 쿼리 끝 구두점의 의미는 완전히 구분하지 못한다.
