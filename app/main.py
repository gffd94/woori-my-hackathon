from fastapi import FastAPI

from app.errors import register_exception_handlers

app = FastAPI()
register_exception_handlers(app)

@app.get("/")
def home():
    return {
        "message": "Hackathon API is running!"
    }
