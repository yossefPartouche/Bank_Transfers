"""Problem 9 · Duplicate transfer on retry.

A client sends a transfer, the response is lost, so it sends the SAME request again
with the SAME Idempotency-Key, plus a double click (two at once). It should be
executed exactly once.

Run:  python -m scripts.chaos.duplicate
PASS when: one transfer exists and the money moved once.
Fix comes at roadmap step 5 (uncomment idempotency_key in the schema and use it).
"""
from app.db import get_conn
from scripts.chaos.common import client, fresh_start, run_concurrently, transfer, verdict

with client() as api:
    _, (a, b) = fresh_start(api, bots=2, start_balance=1_000)
    transfer(api, a, b, 100, key="retry-key-1")                     # first attempt
    transfer(api, a, b, 100, key="retry-key-1")                     # retry after a "lost" response
    run_concurrently([lambda: transfer(api, a, b, 100, key="double-click-1")] * 2)  # double click
    b_balance = api.get(f"/accounts/{b}").json()["balance"]

with get_conn() as conn:
    executed = conn.execute(
        "SELECT COUNT(*) FROM transfers WHERE sender_id = %s AND receiver_id = %s AND status = 'completed'",
        (a, b)).fetchone()[0]

verdict("Problem 9 · duplicate transfer on retry", {
    "extra transfers executed": executed - 2,
    "extra money received": b_balance - 1_200,
}, {"intended transfers": 2, "executed": executed, "receiver balance": b_balance, "expected": 1_200})
