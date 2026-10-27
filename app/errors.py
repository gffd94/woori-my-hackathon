"""요청 원문이나 내부 예외를 포함하지 않는 공통 오류 응답."""

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send


async def request_validation_error_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={
            "detail": {
                "code": "REQUEST_VALIDATION_ERROR",
                "message": "요청 입력을 확인해 주세요.",
            }
        },
    )


async def unexpected_error_handler(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=500,
        content={
            "detail": {
                "code": "INTERNAL_SERVER_ERROR",
                "message": "서버 오류가 발생했습니다.",
            }
        },
    )


class _UnexpectedErrorMiddleware:
    """HTTP 예외를 서버 로그까지 재전파하기 전에 안전한 응답으로 처리한다."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        response_started = False

        async def track_response(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, receive, track_response)
        except Exception as exc:
            if response_started:
                # 이미 보낸 상태 코드는 바꾸지 않고 원래 예외 내용도 재노출하지 않는다.
                raise RuntimeError("응답 처리 중 서버 오류가 발생했습니다.") from None
            response = await unexpected_error_handler(Request(scope, receive), exc)
            await response(scope, receive, send)


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(RequestValidationError, request_validation_error_handler)
    app.add_exception_handler(Exception, unexpected_error_handler)
    app.add_middleware(_UnexpectedErrorMiddleware)
