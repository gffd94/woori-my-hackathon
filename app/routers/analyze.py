"""POST /analyze"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from app.config import load_settings
from app.schemas.analyze import AnalyzeRequest, AnalyzeResponse
from app.services.analyzer import Analyzer, VerdictLogError, build_default_analyzer

router = APIRouter()

# 오류 본문은 feature/error-handling의 {"detail": {"code", "message"}} 형식을 따른다
VERDICT_LOG_UNAVAILABLE = {
    "code": "VERDICT_LOG_UNAVAILABLE",
    "message": "판정 결과를 기록하지 못했습니다. 잠시 후 다시 시도해 주세요.",
}


def get_analyzer() -> Analyzer:
    """요청마다 새로 만든다. 테스트는 app.dependency_overrides로 대역을 넣는다."""
    return build_default_analyzer(load_settings())


@router.post("/analyze", response_model=AnalyzeResponse)
def analyze(body: AnalyzeRequest, analyzer: Annotated[Analyzer, Depends(get_analyzer)]) -> AnalyzeResponse:
    # 동기 함수라 FastAPI가 스레드에서 실행한다 (외부 호출이 이벤트 루프를 막지 않음)
    try:
        return analyzer.analyze(body.message)
    except VerdictLogError:
        # 기록 실패를 200·UNKNOWN으로 숨기지 않는다 (SPEC 2.10)
        raise HTTPException(status_code=503, detail=VERDICT_LOG_UNAVAILABLE) from None
