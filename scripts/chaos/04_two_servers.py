"""Step 4 · Two servers.

In production the API runs as several processes. Each process has its OWN memory and opens
its OWN database connections. Only the database itself is shared.

Scenario A · overdraft on two servers: the overdraft attack from 02_concurrency (scenario C),
split between TWO separate API servers. A lock kept in Python memory (threading.Lock) exists
once per process, so each server would let its own share through. A lock in the database
(SELECT ... FOR UPDATE) is shared by both, so exactly one transfer can succeed.

Scenario B · connection peak: both servers run several workers, and each request opens a
brand-new Postgres connection. Under load, all of them together can open more connections
than Postgres allows (max_connections, about 100), and requests start failing.

Isolation: in B money only flows one way (no deadlock), every account can afford its transfers
(no refusal), and every request has its own idempotency key (no retry).

Starts its own servers (ports 8002 and 8003). The DB is the same for both.
Run:   python -m scripts.chaos.04_two_servers
Fix:   A · keep every lock in the database, never in Python memory (nothing to do if step 2 is right)
       B · a connection pool per worker (psycopg_pool), sized so all workers together stay under the limit
PASS:  A · exactly 1 success, all others refused (422), balance = start - amount, every round
       B · no failed request, and the peak of open connections stays under 80% of the limit
"""
import threading

from app.db import connect
from scripts.chaos.common import (client, fire_at_once, fresh_start, kill_server, run_concurrently,
                                  start_server, tally, transfer, verdict)
from tests.checker import check

PORTS = (8002, 8003)  # two separate API servers, sharing only the database
ROUNDS = 3

# Scenario A (same numbers as 02_concurrency, scenario C)
A_START = 100      # the spender holds 1.00
A_TRIES = 20       # transfers fired at the same moment, half to each server
A_AMOUNT = 80      # 0.80 each: affordable exactly once

# Scenario B
B_WORKERS = 4      # uvicorn workers per server: 2 servers × 4 workers × ~40 requests each
B_REQUESTS = 1200  # transfers in total
B_IN_FLIGHT = 250  # transfers in flight at the same time
B_PAIRS = 100      # sender i always pays receiver i: one-way, no shared receiver
B_WARNING = 0.8    # the peak must stay under 80% of max_connections


def two_servers(workers):
    """Start one API server per port. Returns (processes, clients)."""
    procs = [start_server(port, workers=workers) for port in PORTS]
    apis = [client(f"http://localhost:{port}") for port in PORTS]
    return procs, apis


def stop(procs, apis):
    for api in apis:
        api.close()
    for proc in procs:
        kill_server(proc)


# ---------- scenario A ----------

def overdraft_two_servers(apis):
    """Scenario A, one round. Returns a dict of numbers for the verdict."""
    _, (spender, *receivers) = fresh_start(bots=1 + A_TRIES, start_balance=A_START)
    codes = fire_at_once(apis, [(spender, r, A_AMOUNT) for r in receivers])  # alternates between servers

    return {
        **tally(codes),
        "balance": apis[0].get(f"/accounts/{spender}").json()["balance"],
        "broken": [name for name, _ in check()],
    }


# ---------- scenario B ----------

def connection_peak(apis):
    """Scenario B. Returns a dict of numbers for the verdict."""
    _, bots = fresh_start(bots=2 * B_PAIRS, start_balance=10_000)
    senders, receivers = bots[:B_PAIRS], bots[B_PAIRS:]

    with connect() as conn:
        limit = int(conn.execute("SHOW max_connections").fetchone()[0])

    peak = 0
    done = threading.Event()

    def watch():
        """Count open connections to our database, as often as possible, until done."""
        nonlocal peak
        with connect(autocommit=True) as conn:
            while not done.is_set():
                n = conn.execute(
                    "SELECT count(*) FROM pg_stat_activity WHERE datname = current_database()"
                ).fetchone()[0]
                peak = max(peak, n)

    def send(i):
        api = apis[i % len(apis)]            # alternate between the two servers
        pair = i % B_PAIRS
        return transfer(api, senders[pair], receivers[pair], 1)

    watcher = threading.Thread(target=watch)
    watcher.start()
    results = run_concurrently([lambda i=i: send(i) for i in range(B_REQUESTS)], workers=B_IN_FLIGHT)
    done.set()
    watcher.join()

    codes = [r.status_code if not isinstance(r, Exception) else "error" for r in results]
    return {**tally(codes), "peak": peak, "limit": limit, "broken": [name for name, _ in check()]}


if __name__ == "__main__":
    procs, apis = two_servers(workers=1)
    try:
        a = [overdraft_two_servers(apis) for _ in range(ROUNDS)]
    finally:
        stop(procs, apis)

    procs, apis = two_servers(workers=B_WORKERS)
    try:
        b = connection_peak(apis)
    finally:
        stop(procs, apis)

    verdict("Step 4 · two servers", {
        "A · rounds with more than 1 success": sum(r["succeeded"] > 1 for r in a),
        "A · rounds with answers other than 201/422": sum(r["other"] > 0 for r in a),
        "A · rounds with a wrong final balance": sum(r["balance"] != A_START - A_AMOUNT for r in a),
        "A · rounds with broken invariants": sum(bool(r["broken"]) for r in a),
        "B · failed requests (not 201)": b["refused"] + b["other"],
        "B · connections above the 80% warning line": max(0, b["peak"] - int(b["limit"] * B_WARNING)),
        "B · broken invariants": len(b["broken"]),
    }, details={
        "rounds (A)": ROUNDS,
        "servers": ", ".join(f"localhost:{p}" for p in PORTS),
        "A · (succeeded, refused, other) per round": ", ".join(
            f"({r['succeeded']}, {r['refused']}, {r['other']})" for r in a),
        "A · final balance per round (expected 20)": ", ".join(str(r["balance"]) for r in a),
        "B · load": f"{B_REQUESTS} transfers, {B_IN_FLIGHT} in flight, {len(PORTS)} servers × {B_WORKERS} workers",
        "B · (succeeded, refused, other)": f"({b['succeeded']}, {b['refused']}, {b['other']})",
        "B · peak open connections / limit": f"{b['peak']} / {b['limit']}",
    }, invariants=False)  # each scenario ran the checker itself; the DB is reset in between