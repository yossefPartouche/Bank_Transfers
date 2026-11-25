from app.db import get_conn
from scripts.reset_db import reset_db


def seed(accounts=None):
    " Seed the database with initial data. If accounts is None, default accounts A and B are created with 10000 each."
    accounts = accounts or {"A": 10000, "B": 10000}
    ids = {}
    with get_conn() as conn:
        # Create a system account for the bank
        ids["bank"] = conn.execute( 
            "INSERT INTO accounts (owner, is_system) VALUES ('bank', true) RETURNING id"
        ).fetchone()[0]

        # for each account in the accounts dictionary, create an account and a transfer from the bank to that account
        for owner, amount in accounts.items():
            # Create the account and transfer from the bank to that account
            acc = conn.execute(
                "INSERT INTO accounts (owner) VALUES (%s) RETURNING id", (owner,)
            ).fetchone()[0]
            
            # Create a transfer from the bank to the account and update the ledger and balances
            t = conn.execute(
                "INSERT INTO transfers (sender_id, receiver_id, amount, status) "
                "VALUES (%s, %s, %s, 'completed') RETURNING id",
                (ids["bank"], acc, amount),
            ).fetchone()[0]
            
            # Update the ledger and balances
            conn.execute(
                "INSERT INTO ledger_entries (transfer_id, account_id, amount) "
                "VALUES (%s, %s, %s), (%s, %s, %s)",
                (t, ids["bank"], -amount, t, acc, amount),
            )
            conn.execute("UPDATE accounts SET balance = balance - %s WHERE id = %s", (amount, ids["bank"]))
            conn.execute("UPDATE accounts SET balance = balance + %s WHERE id = %s", (amount, acc))
            ids[owner] = acc

    print(f"Seeded: {ids}")
    return ids


if __name__ == "__main__":
    reset_db()
    seed()