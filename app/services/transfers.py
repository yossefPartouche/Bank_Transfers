from app.db import get_conn
from app.errors import AccountNotFound, InsufficientFunds, InvalidAmount, SameAccount


def transfer(sender_id, receiver_id, amount):
    # Step 1: one transaction. Step 2 (partial): balances computed in the DB.
    # Still deciding on a stale balance (overdraft, problem 3) and no idempotency key.
    if amount <= 0:
        raise InvalidAmount("amount must be a positive whole number")
    if sender_id == receiver_id:
        raise SameAccount("sender and receiver must be different")

    with get_conn() as conn:
        # read the balances
        sender = conn.execute(
            "SELECT balance, is_system FROM accounts WHERE id = %s", (sender_id,)
        ).fetchone()
        receiver = conn.execute(
            "SELECT balance FROM accounts WHERE id = %s", (receiver_id,)
        ).fetchone()
        if sender is None or receiver is None:
            raise AccountNotFound("sender or receiver does not exist")

        sender_balance, sender_is_system = sender

        # check for insufficient funds (unless the sender is a system account)
        if not sender_is_system and sender_balance < amount:
            conn.execute(
                "INSERT INTO transfers (sender_id, receiver_id, amount, status) "
                "VALUES (%s, %s, %s, 'refused')",
                (sender_id, receiver_id, amount),
            )
            raise InsufficientFunds(f"account {sender_id} has {sender_balance}, needs {amount}")

        # create the transfer and ledger entries, update balances
        transfer_id, created_at = conn.execute(
            "INSERT INTO transfers (sender_id, receiver_id, amount, status) "
            "VALUES (%s, %s, %s, 'completed') RETURNING id, created_at",
            (sender_id, receiver_id, amount),
        ).fetchone()
        conn.execute(
            "INSERT INTO ledger_entries (transfer_id, account_id, amount) VALUES (%s, %s, %s)",
            (transfer_id, sender_id, -amount),
        )
        conn.execute(
            "INSERT INTO ledger_entries (transfer_id, account_id, amount) VALUES (%s, %s, %s)",
            (transfer_id, receiver_id, amount),
        )
        # Step 2: the DB computes the new balance from the current value, not from our copy.
        conn.execute("UPDATE accounts SET balance = balance - %s WHERE id = %s", (amount, sender_id))
        conn.execute("UPDATE accounts SET balance = balance + %s WHERE id = %s", (amount, receiver_id))
        # This is neccessary since it happens automatically, though better for readability 
        conn.commit()

    return {"id": transfer_id, "sender_id": sender_id, "receiver_id": receiver_id,
            "amount": amount, "status": "completed", "created_at": created_at}