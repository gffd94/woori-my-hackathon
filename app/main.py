from fastapi import FastAPI

from app.routers.analyze import router as analyze_router

app = FastAPI()
app.include_router(analyze_router)

@app.get("/")
def home():
    return {
        "message": "Hackathon API is running!"
    }
