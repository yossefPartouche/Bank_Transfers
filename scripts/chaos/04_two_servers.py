"""Step 4 · Two servers.

In production the API runs as several processes. Each process has its 
OWN memory: a lock, counter or cache kept in a Python variable exists once per process,
this protects nothing across them. Only what lives in the database is shared.

Scenario A · overdraft on two servers: the overdraft attack from 02_concurrency, but the
requests are split between TWO separate API servers (ports 8002 and 8003). If the protection
lived in Python memory (e.g. threading.Lock), each server would let its own share through.

Starts its own two servers. The DB is the same for both.
Run:   python -m scripts.chaos.04_two_servers
Fix:   keep every lock in the database (SELECT ... FOR UPDATE), never in Python memory.
       Nothing to do if step 2 is done right: this script PROVES it.
PASS:  A · exactly 1 success, all others refused (422), balance = start - amount, every round
"""
import threading

from scripts.chaos.common import (client, fresh_start, kill_server, run_concurrently, start_server,
                                  transfer, verdict)
from tests.checker import check

PORTS = (8002, 8003)  # two separate API processes, sharing only the database
ROUNDS = 3

# Scenario A (same numbers as 02_concurrency, scenario C)
A_START = 100      # the spender holds 1.00
A_TRIES = 20       # transfers fired at the same moment, half to each server
A_AMOUNT = 80      # 0.80 each: affordable exactly once


def all_at_once_split(apis, calls):
    """Fire every call at the same moment, alternating between the servers in `apis`.

    Call 0 goes to server 1, call 1 to server 2, call 2 to server 1... so each server
    gets half of the attack, guaranteed (not left to chance).
    """
    barrier = threading.Barrier(len(calls))

    def job(i, sender, receiver, amount):
        api = apis[i % len(apis)]
        barrier.wait()
        return transfer(api, sender, receiver, amount)

    results = run_concurrently(
        [lambda i=i, c=c: job(i, *c) for i, c in enumerate(calls)],
        workers=len(calls),
    )
    return [r.status_code if not isinstance(r, Exception) else "error" for r in results]


def overdraft_two_servers(apis):
    """Scenario A, one round. Returns a dict of numbers for the verdict."""
    _, (spender, *receivers) = fresh_start(bots=1 + A_TRIES, start_balance=A_START)
    codes = all_at_once_split(apis, [(spender, r, A_AMOUNT) for r in receivers])

    return {
        "succeeded": codes.count(201),
        "refused": codes.count(422),
        "other": len(codes) - codes.count(201) - codes.count(422),
        "balance": apis[0].get(f"/accounts/{spender}").json()["balance"],
        "broken invariants": [name for name, _ in check()],
    }


if __name__ == "__main__":
    servers = [start_server(port) for port in PORTS]
    try:
        apis = [client(f"http://localhost:{port}") for port in PORTS]
        a = [overdraft_two_servers(apis) for _ in range(ROUNDS)]
        for api in apis:
            api.close()
    finally:
        for proc in servers:
            kill_server(proc)

    verdict("Step 4 · two servers", {
        "A · rounds with more than 1 success": sum(r["succeeded"] > 1 for r in a),
        "A · rounds with answers other than 201/422": sum(r["other"] > 0 for r in a),
        "A · rounds with a wrong final balance": sum(r["balance"] != A_START - A_AMOUNT for r in a),
        "A · rounds with broken invariants": sum(bool(r["broken invariants"]) for r in a),
    }, details={
        "rounds": ROUNDS,
        "servers": ", ".join(f"localhost:{p}" for p in PORTS),
        "A · (succeeded, refused, other) per round": ", ".join(
            f"({r['succeeded']}, {r['refused']}, {r['other']})" for r in a),
        "A · final balance, per round (expected 20)": ", ".join(str(r["balance"]) for r in a),
        "A · invariants broken (last round)": ", ".join(a[-1]["broken invariants"]) or "none",
    }, invariants=False)