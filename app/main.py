import psycopg
from fastapi.responses import JSONResponse
from fastapi import FastAPI
from app.db import get_conn
from pydantic import BaseModel
app = FastAPI()

def error(status: int, code: str, message: str) -> JSONResponse:
    """Every error in the contract's shape: {"error": {"code", "message"}}."""
    return JSONResponse(status_code=status, content={"error": {"code": code, "message": message}})

class AccountIn(BaseModel):
    owner: str

@app.get("/health")
def health():
    try:
        with get_conn() as conn:           # Use the get_conn function to get a db connection
            conn.execute("SELECT 1")
    except psycopg.OperationalError:
        return JSONResponse(status_code=503, content={"status": "error"})
    return {"status": "ok"}

@app.post("/accounts", status_code=201)
def create_account(body: AccountIn):
    try:
        with get_conn() as conn:
            row = conn.execute(
                "INSERT INTO accounts (owner) VALUES (%s) "
                "RETURNING id, owner, balance, created_at",
                (body.owner,),
            ).fetchone()
    except psycopg.errors.CheckViolation:
        return error(400, "invalid_owner", "owner must not be empty")
    except psycopg.errors.UniqueViolation:
        return error(409, "owner_taken", f"an account for '{body.owner}' already exists")

    return {"id": row[0], "owner": row[1], "balance": row[2], "created_at": row[3]}

@app.get("/accounts/{account_id}")
def get_account(account_id: int):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT id, owner, balance FROM accounts WHERE id = %s",
            (account_id,),
        ).fetchone()

    if row is None:
        return error(404, "account_not_found", f"no account with id {account_id}")

    return {"id": row[0], "owner": row[1], "balance": row[2]}