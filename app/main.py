from fastapi import FastAPI

from app.errors import register_exception_handlers
from app.routers.analyze import router as analyze_router

app = FastAPI()
register_exception_handlers(app)
app.include_router(analyze_router)

@app.get("/")
def home():
    return {
        "message": "Hackathon API is running!"
    }
