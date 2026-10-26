from fastapi import FastAPI

app = FastAPI()

@app.get("/")
def home():
    return {
        "message": "Hackathon API is running!"
    }python -m uvicorn app.main:app --reload