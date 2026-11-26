"""Step 1 · Crash in the middle of a transfer.

A transfer is several SQL statements. Without a transaction each one commits on its own,
so anything that interrupts a transfer, or looks at it halfway, sees a broken state.

Scenario A · power cut: ONE client sends transfers one after the other (no concurrency,
so the only possible cause is the crash) and we SIGKILL the server several times mid-run.
Scenario B · reader in the middle: transfers run while a reader keeps summing all balances.
Every pair of accounts is used by one job only (no shared account, so no lost update).

Run:   python -m scripts.chaos.01_crash      (starts its own server on port 8001)
Fix:   one transaction around the whole transfer, in services/transfers.py
PASS:  A · no half-written transfer, the money still sums to 0
       B · the reader never sees a total other than 0
"""
import random
import threading

import httpx

from app.db import connect
from scripts.chaos.common import client, fresh_start, kill_server, run_concurrently, start_server, transfer, verdict
from tests.checker import check

PORT = 8001      # for his own server
POWER_CUTS = 10  # cutpower 10 times, each time after a random number of transfers (0.2-0.6s)
PAIRS = 150      # scenario b : create 300 accounts  (paire 1 : bot-0  ↔ bot-1 ; paire 2 : bot-2  ↔ bot-3)
ROUND_TRIPS = 10 # each pair does 10 round trips 


def power_cut():
    """Scenario A. Returns the invariants broken after the crashes."""
    _, (a, b) = fresh_start(bots=2, start_balance=1_000_000)  # one pair of accounts, each with 1M
    
    for _ in range(POWER_CUTS):
        proc = start_server(PORT)
        threading.Timer(random.uniform(0.2, 0.6), kill_server, args=(proc,)).start()
        with client(f"http://localhost:{PORT}") as api:
            sender, receiver = a, b
            
            while True:         # keep sending transfers until the server is killed
                try:
                    transfer(api, sender, receiver, 1)
                except httpx.HTTPError:
                    break  # the server is gone: power cut
                sender, receiver = receiver, sender         #swap the sender and receiver for the next transfer
    return check()


def reader_in_the_middle():
    """Scenario B. Returns (reads, reads that saw a wrong total)."""
    _, bots = fresh_start(bots=2 * PAIRS, start_balance=10_000)     # 2 * PAIRS accounts
    
    pairs = list(zip(bots[::2], bots[1::2]))  # each account belongs to exactly one pair
    stop = threading.Event()         # flag to tell the reader to stop when the transfers are done
    reads = wrong = 0

    def reader():
        "add up all balances, keep track of how many reads and how many were wrong"
        nonlocal reads, wrong
        with connect(autocommit=True) as conn:  # every read sees the latest committed state
            while not stop.is_set():
                total = conn.execute("SELECT sum(balance) FROM accounts").fetchone()[0]
                reads += 1
                wrong += total != 0

    def back_and_forth(api, x, y):
        "one pair of accounts does several round trips, each time sending 1 from x to y and back"
        for _ in range(ROUND_TRIPS):  # sequential inside the pair: no lost update possible
            transfer(api, x, y, 1)
            transfer(api, y, x, 1)

    proc = start_server(PORT)
    try:
        watcher = threading.Thread(target=reader)   # start the reader in the background
        watcher.start()
        with client(f"http://localhost:{PORT}") as api:
            # 150 pairs of accounts, each doing 10 round trips
            run_concurrently([lambda x=x, y=y: back_and_forth(api, x, y) for x, y in pairs], workers=10)
        stop.set()      # tell the reader to stop, but it may still be in the middle of a read
        watcher.join()
    finally:
        kill_server(proc)  # turn off api
    return reads, wrong


if __name__ == "__main__":
    broken = power_cut()
    reads, wrong = reader_in_the_middle()
    verdict("Step 1 · crash in the middle", {
        "A · invariants broken after power cuts": len(broken),
        "B · reads that saw a wrong total": wrong,
    }, details={
        "power cuts": POWER_CUTS,
        "A · which invariants": ", ".join(name for name, _ in broken) or "none",
        "B · total reads": reads,
    }, invariants=False)  # A already ran the checker; B's DB is a different run