import psycopg

from app.db import get_conn
from app.errors import AccountNotFound, InvalidOwner, OwnerTaken


def create_account(owner):
    try:
        with get_conn() as conn:
            row = conn.execute(
                "INSERT INTO accounts (owner) VALUES (%s) RETURNING id, owner, balance, created_at",
                (owner,),
            ).fetchone()
    except psycopg.errors.CheckViolation:
        raise InvalidOwner("owner must not be empty")
    except psycopg.errors.UniqueViolation:
        raise OwnerTaken(f"an account for '{owner}' already exists")
    return {"id": row[0], "owner": row[1], "balance": row[2], "created_at": row[3]}


def get_account(account_id):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT id, owner, balance FROM accounts WHERE id = %s", (account_id,)
        ).fetchone()
    if row is None:
        raise AccountNotFound(f"no account with id {account_id}")
    return {"id": row[0], "owner": row[1], "balance": row[2]}