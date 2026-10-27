from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import load_frontend_origins
from app.errors import register_exception_handlers
from app.routers.analyze import router as analyze_router

app = FastAPI()
register_exception_handlers(app)
# 나중에 등록한 CORS가 오류 처리 미들웨어를 감싸 422·500에도 헤더를 붙인다.
app.add_middleware(
    CORSMiddleware,
    allow_origins=load_frontend_origins(),
    allow_methods=["POST"],
    allow_headers=["Content-Type"],
    allow_credentials=False,
)
app.include_router(analyze_router)

@app.get("/")
def home():
    return {
        "message": "Hackathon API is running!"
    }
