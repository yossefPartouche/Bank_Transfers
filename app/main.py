from fastapi import FastAPI

from app.db import get_conn

app = FastAPI()


@app.get("/health")
def health():
    with get_conn() as conn:           # Use the get_conn function to get a database connection
        conn.execute("SELECT 1")
    return {"status": "ok"}