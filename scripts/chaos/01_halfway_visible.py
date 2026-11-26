"""Problem 1.1 · Halfway states visible to readers.

Transfers run while a "watcher" keeps adding up all balances. Each step of a
transfer commits on its own, so the watcher can land between "sender debited" and
"receiver credited" and see money that is temporarily missing or extra.

Run:  python -m scripts.chaos.01_halfway_visible
PASS when: the watcher never sees a total other than 0.
Note: with lost updates still present (problems 1-2), the final total can be wrong
too; this script only counts what readers saw DURING the run.
"""
import threading

from app.db import get_conn
from scripts.chaos.common import client, fresh_start, run_concurrently, transfer, verdict

TRANSFERS = 300
seen_wrong, reads = 0, 0
stop = threading.Event()


def watcher():
    global seen_wrong, reads
    with get_conn() as conn:
        conn.autocommit = True  # every read sees the latest committed state
        while not stop.is_set():
            total = conn.execute("SELECT SUM(balance) FROM accounts").fetchone()[0]
            reads += 1
            seen_wrong += total != 0


with client() as api:
    _, bots = fresh_start(api, bots=40, start_balance=10_000)
    # pairs of distinct accounts so lost updates are rare and the halfway states stand out
    jobs = [lambda i=i: transfer(api, bots[i % 20], bots[20 + i % 20], 1) for i in range(TRANSFERS)]
    t = threading.Thread(target=watcher)
    t.start()
    run_concurrently(jobs, workers=10)
    stop.set()
    t.join()

verdict("Problem 1.1 · halfway states visible", {
    "reads that saw a wrong total": seen_wrong,
}, {"total reads during the run": reads})
