import psycopg
from fastapi.responses import JSONResponse
from fastapi import FastAPI

from app.db import get_conn

app = FastAPI()


@app.get("/health")
def health():
    try:
        with get_conn() as conn:           # Use the get_conn function to get a db connection
            conn.execute("SELECT 1")
    except psycopg.OperationalError:
        return JSONResponse(status_code=503, content={"status": "error"})
    return {"status": "ok"}