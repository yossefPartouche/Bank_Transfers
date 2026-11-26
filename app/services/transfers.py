from app.db import get_conn
from app.errors import AccountNotFound, InsufficientFunds, InvalidAmount, SameAccount


def transfer(sender_id, receiver_id, amount):
    # Step 1: one transaction. Step 2: rows locked before deciding, balances computed in the DB.
    # Step 3: rows locked in id order. Not yet: idempotency key (step 5).
    if amount <= 0:
        raise InvalidAmount("amount must be a positive whole number")
    if sender_id == receiver_id:
        raise SameAccount("sender and receiver must be different")

    with get_conn() as conn:
        # Lock both rows: other transfers on these accounts wait until we commit, then read
        # the up-to-date balance (see docs/decisions/step-02-locking.md).
        # we've removed the circular waiting by making the waiting descision on the id ordering
        # Obstructing one of the conditions in Coffmans conditions in deadlock
        locked = {}
        for account_id in sorted((sender_id, receiver_id)):
            row = conn.execute("SELECT id, balance, is_system FROM accounts WHERE id = %s FOR UPDATE", 
                               (account_id,)).fetchone()
            if row is None:
                raise AccountNotFound("sender or receiver does not exist")
            locked[account_id] = row
        sender = locked[sender_id][1:]
        sender_balance, sender_is_system = sender

        # check for insufficient funds (unless the sender is a system account)
        if not sender_is_system and sender_balance < amount:
            conn.execute(
                "INSERT INTO transfers (sender_id, receiver_id, amount, status) "
                "VALUES (%s, %s, %s, 'refused')",
                (sender_id, receiver_id, amount),
            )
            conn.commit()  # keep the refusal: the exception below would roll it back
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
        
        
        conn.commit()  # explicit for readability; leaving the `with` would commit anyway

    return {"id": transfer_id, "sender_id": sender_id, "receiver_id": receiver_id,
            "amount": amount, "status": "completed", "created_at": created_at}