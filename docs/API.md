# 문자 분석 API

## POST /analyze

요청: `{"message": "분석할 가상 문자", "source": "paste"}`. source는 paste 또는 share이며 생략하면 paste다.

기존 응답 `status`, `risk_level`, `reasons`, `matched_cases`, `guide_type`, `retrieval`을 유지하고 `evidence` 배열을 추가한다.

```json
{
  "kind": "pattern",
  "title": "가상 배송 사칭 수법",
  "detail": "분석에 참고한 유사 수법이에요. 문자 속 링크의 악성 여부를 직접 증명하는 자료는 아니에요.",
  "value": null,
  "sources": [{
    "title": "가상 안내 자료",
    "site": "가상 자료실",
    "url": "https://reference.example/post/7",
    "posted_date": "2026-10-28"
  }]
}
```

위 객체는 evidence 배열 안의 한 항목 예시이며, 실제 URL이나 기관을 나타내지 않는다.

| kind | 의미 | 출처 연결 |
|---|---|---|
| indicator_match | 등록된 악성 URL·도메인·전화번호 대조 일치 | 현행 indicators에 출처 관계가 없어 빈 배열 |
| official_match | 공식 도메인 대조 일치 | official_links의 기관명·확인 근거 |
| unverified | 공식 정보로 확인되지 않은 요소 | 빈 배열. 악성 확정 의미 아님 |
| signal | 입력에서 확인된 AI 신호와 문구 | 빈 배열. 외부 자료 인용이 아님 |
| pattern | 완료된 검색에서 참고한 유사 수법 | pattern_sources로 연결된 sources 메타데이터 |

- `value`는 개인정보·URL 민감 부분을 마스킹한다. 입력 전체·자료 본문·검색 점수·내부 ID는 반환하지 않는다.
- 출처가 없으면 `sources: []`, 사용할 수 있는 HTTPS 주소가 없으면 `url: null`이다. 공개 게시글 ID 쿼리는 유지하지만 인증용 URL은 제외한다.
- 검색 실패·제한·미실행이면 수법 근거를 반환하지 않는다. 검색 완료 후 LLM 실패 시 검색된 참고 자료는 유지하지만 AI 신호는 표시하지 않는다.
- 출처 메타데이터 조회 실패도 검색 실패로 처리한다. 최종 판정 우선순위와 기록 commit 실패 시 503 동작은 유지한다.
- 유사 수법 자료는 해당 문자가 사기라는 직접 증명이 아니다. 공식 도메인 일치도 문자 전체의 안전을 보장하지 않는다.
- 프론트엔드는 evidence가 없는 이전 응답도 표시한다. 샘플 모드는 시연용임을 명시하고 실제 자료 출처를 꾸며내지 않는다.

## 검증 범위

DB/외부 API를 차단한 API·서비스·SQL 대역 테스트와 React 렌더링 테스트로 검증한다. 실제 DB 스키마·적재된 출처·LLM 연결 및 브라우저 시각 검증과는 구분한다.

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_evidence_sources.py tests/test_repository.py tests/test_analyze_flow.py tests/test_analyze_api.py tests/test_cors.py tests/test_schemas.py tests/test_masking.py tests/test_final_decision.py tests/test_error_handling.py -q
cd frontend
node --test src/api/resultDetails.test.js src/components/EvidenceDetails.test.js
npm.cmd run build
```
