from fastapi import FastAPI
from app.database import engine, Base

app = FastAPI()

@app.get("/")
def read_root():
    return {"message": "TBS Timetable Backend Online"}