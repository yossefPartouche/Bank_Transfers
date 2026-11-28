from app.db import get_conn
from app.errors import AccountNotFound, InsufficientFunds, InvalidAmount, SameAccount, IdempotencyKeyReused
import psycopg

def _previous_answer(conn, idempotency_key, request):
    """If this key was already handled, the answer given the first time; otherwise None."""
    if idempotency_key is None:
        return None
    row = conn.execute(
        "SELECT id, sender_id, receiver_id, amount, status, created_at "
        "FROM transfers WHERE idempotency_key = %s",
        (idempotency_key,),
    ).fetchone()
    if row is None:
        return None
    transfer_id, sender_id, receiver_id, amount, status, created_at = row
    if (sender_id, receiver_id, amount) != request :
        raise IdempotencyKeyReused(f"key {idempotency_key} was already used for a different transfer")
    if status == "refused":
        raise InsufficientFunds(f"transfer with key {idempotency_key} was already refused")
    return {"id": transfer_id, "sender_id": sender_id, "receiver_id": receiver_id,
            "amount": amount, "status": status, "created_at": created_at}

def transfer(sender_id, receiver_id, amount, idempotency_key=None):
    """Step 5: if two requests with the same key race (double click), both may pass the
    "already handled?" check; the UNIQUE key then lets only one insert succeed. The loser
    gets a UniqueViolation: it answers exactly as the winner did, instead of a 500."""
    try:
        return _transfer(sender_id, receiver_id, amount, idempotency_key)
    except psycopg.errors.UniqueViolation as e:
        if e.diag.constraint_name != "transfers_idempotency_key_key":
            raise  # some other unique rule broke: a real bug, don't hide it
        with get_conn() as conn:  # the winner has committed by now: read its answer
            return _previous_answer(conn, idempotency_key, (sender_id, receiver_id, amount))

def _transfer(sender_id, receiver_id, amount, idempotency_key=None):
    # Step 1: one transaction. Step 2: rows locked before deciding, balances computed in the DB.
    # Step 3: rows locked in id order. Not yet: idempotency key (step 5).
    # step 5: idempotency key in progress 
    if amount <= 0:
        raise InvalidAmount("amount must be a positive whole number")
    if sender_id == receiver_id:
        raise SameAccount("sender and receiver must be different")

    with get_conn() as conn:
        # Step 5: a key we've already handled gets the same answer again, with no new transfer.
        # (`:=` assigns and tests in one line)
        if (previous := _previous_answer(conn, idempotency_key, (sender_id, receiver_id, amount))):
            # The := is an assingment and checker at the same time
            return previous
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
                "INSERT INTO transfers (idempotency_key, sender_id, receiver_id, amount, status) "
                "VALUES (%s, %s, %s, %s, 'refused')",
                (idempotency_key, sender_id, receiver_id, amount),
            )
            conn.commit()  # keep the refusal: the exception below would roll it back
            raise InsufficientFunds(f"account {sender_id} has {sender_balance}, needs {amount}")
        
        # create the transfer and ledger entries, update balances
        transfer_id, created_at = conn.execute(
            "INSERT INTO transfers (idempotency_key, sender_id, receiver_id, amount, status) "
            "VALUES (%s, %s, %s, %s, 'completed') RETURNING id, created_at",
            (idempotency_key, sender_id, receiver_id, amount),
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