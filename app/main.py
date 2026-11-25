import psycopg
from fastapi.responses import JSONResponse
from fastapi import FastAPI
from app.db import get_conn, DATABASE_URL
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
class TransferIn(BaseModel):
    sender_id: int
    receiver_id: int
    amount: int


@app.post("/transfers", status_code=201)
def create_transfer(body: TransferIn):
    # NAIVE on purpose: no transaction, no lock, no idempotency key.
    # Each statement commits on its own (autocommit), so the bugs can show up.
    if body.amount <= 0:
        return error(400, "invalid_amount", "amount must be a positive whole number")
    if body.sender_id == body.receiver_id:
        return error(400, "same_account", "sender and receiver must be different")

    with psycopg.connect(DATABASE_URL, autocommit=True) as conn:
        sender = conn.execute(
            "SELECT balance, is_system FROM accounts WHERE id = %s", (body.sender_id,)
        ).fetchone()
        receiver = conn.execute(
            "SELECT balance FROM accounts WHERE id = %s", (body.receiver_id,)
        ).fetchone()
        if sender is None or receiver is None:
            return error(404, "account_not_found", "sender or receiver does not exist")

        sender_balance, sender_is_system = sender
        receiver_balance = receiver[0]

        if not sender_is_system and sender_balance < body.amount:
            conn.execute(
                "INSERT INTO transfers (sender_id, receiver_id, amount, status) "
                "VALUES (%s, %s, %s, 'refused')",
                (body.sender_id, body.receiver_id, body.amount),
            )
            return error(422, "insufficient_funds",
                         f"account {body.sender_id} has {sender_balance}, needs {body.amount}")

        transfer_id = conn.execute(
            "INSERT INTO transfers (sender_id, receiver_id, amount, status) "
            "VALUES (%s, %s, %s, 'completed') RETURNING id, created_at",
            (body.sender_id, body.receiver_id, body.amount),
        ).fetchone()
        conn.execute(
            "INSERT INTO ledger_entries (transfer_id, account_id, amount) VALUES (%s, %s, %s)",
            (transfer_id[0], body.sender_id, -body.amount),
        )
        conn.execute(
            "INSERT INTO ledger_entries (transfer_id, account_id, amount) VALUES (%s, %s, %s)",
            (transfer_id[0], body.receiver_id, body.amount),
        )
        # Read-then-write: new balances computed in Python from the values read above.
        conn.execute("UPDATE accounts SET balance = %s WHERE id = %s",
                     (sender_balance - body.amount, body.sender_id))
        conn.execute("UPDATE accounts SET balance = %s WHERE id = %s",
                     (receiver_balance + body.amount, body.receiver_id))

    return {
        "id": transfer_id[0],
        "sender_id": body.sender_id,
        "receiver_id": body.receiver_id,
        "amount": body.amount,
        "status": "completed",
        "created_at": transfer_id[1],
    }