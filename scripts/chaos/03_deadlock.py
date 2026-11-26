"""Step 3 · Deadlock between opposite transfers.

A→B locks A then B; B→A locks B then A. Fired at the same moment, each one holds the account
the other needs and both wait, until Postgres detects the cycle (after ~1 s) and kills one:
the client gets a 500 and both accounts are frozen meanwhile.

Isolation: both accounts are rich (no refusal), every request has its own idempotency key
(no retry), the server never crashes, lost updates are fixed (step 2). Only a deadlock can fail.

Run:   python -m scripts.chaos.03_deadlock      (needs the API on API_URL, default port 8000)
Fix:   always lock the two accounts in the same order (lowest id first), in services/transfers.py
PASS:  in every round, 0 deadlocks counted by Postgres, every transfer answered 201,
       balances exact, invariants hold
"""
import time

from app.db import get_conn
from scripts.chaos.common import fire_at_once, client, fresh_start, verdict, tally
from tests.checker import check

ROUNDS = 2          # deadlocks depend on timing: a PASS must hold every round
START = 1_000_000   # 10,000.00 € each: nobody can run out of money
EACH_WAY = 10       # 10 A→B and 10 B→A, fired at the same moment
AMOUNT = 100        # 1.00 € each


def deadlocks_so_far():
    """Postgres counts every deadlock it detects, per database."""
    with get_conn() as conn:
        return conn.execute(
            "SELECT deadlocks FROM pg_stat_database WHERE datname = current_database()"
        ).fetchone()[0]


def one_round(api):
    _, (a, b) = fresh_start(bots=2, start_balance=START)
    calls = [(a, b, AMOUNT)] * EACH_WAY + [(b, a, AMOUNT)] * EACH_WAY   # A→B first, then B→A

    before = deadlocks_so_far()
    start = time.perf_counter()
    codes = fire_at_once(api, calls)     # run the transfers at the same moment
    seconds = time.perf_counter() - start
    time.sleep(1.5)  # Postgres publishes its statistics with a short delay
    deadlocks = deadlocks_so_far() - before

    a_to_b = tally(codes[:EACH_WAY])["succeeded"]   # how many successful A→B
    b_to_a = tally(codes[EACH_WAY:])["succeeded"]   # how many successful B→A
    # calculate the expected balances after all the transfers, in order (A, B)
    expected = [START - (a_to_b - b_to_a) * AMOUNT, START + (a_to_b - b_to_a) * AMOUNT]
    # check the actual balances, in order (A, B)
    balances = [api.get(f"/accounts/{x}").json()["balance"] for x in (a, b)]

    return {
        "deadlocks": deadlocks,
        "failed": len(codes) - a_to_b - b_to_a,
        "seconds": seconds,
        "balance wrong": balances != expected,
        "broken": [name for name, _ in check()],
    }


if __name__ == "__main__":
    with client(timeout=10) as api:
        rounds = [one_round(api) for _ in range(ROUNDS)]

    verdict("Step 3 · deadlock between opposite transfers", {
        "rounds with deadlocks (pg_stat_database)": sum(r["deadlocks"] > 0 for r in rounds),
        "rounds with failed transfers (not 201)": sum(r["failed"] > 0 for r in rounds),
        "rounds with a wrong balance": sum(r["balance wrong"] for r in rounds),
        "rounds with broken invariants": sum(bool(r["broken"]) for r in rounds),
    }, details={
        "rounds": ROUNDS,
        "per round": f"{EACH_WAY} A→B + {EACH_WAY} B→A of 1.00 € at the same moment",
        "deadlocks per round": ", ".join(str(r["deadlocks"]) for r in rounds),
        "failed transfers per round": ", ".join(str(r["failed"]) for r in rounds),
        "seconds per round": ", ".join(f"{r['seconds']:.1f}" for r in rounds),
    }, invariants=False)  # each round ran the checker itself; the DB is reset between rounds