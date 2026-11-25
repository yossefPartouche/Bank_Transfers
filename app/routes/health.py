import psycopg
from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.db import get_conn

router = APIRouter()


@router.get("/health")
def health():
    try:
        with get_conn() as conn:
            conn.execute("SELECT 1")
    except psycopg.OperationalError:
        return JSONResponse(status_code=503, content={"status": "error"})
    return {"status": "ok"}