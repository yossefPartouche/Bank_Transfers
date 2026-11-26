""" Problem 1.0 · Crash partway through a transfer.

Starts its OWN API server (port 8001), fires transfers, and kills the server with
SIGKILL in the middle, like a power cut. Because each step commits on its own, some
transfers are left half-written: a transfer without ledger lines (6), ledger lines
without balance updates (7), or one balance updated but not the other (8).

Run:  python -m scripts.chaos.crash
PASS when: after the crash, every completed transfer has exactly 2 ledger lines,
every balance matches its ledger, and the money still sums to 0.
"""
import threading

from scripts.chaos.common import (client, fresh_start, kill_server, money_report, run_concurrently,
                                  start_server, transfer, verdict)

PORT = 8001
ROUNDS = 5  # crash several times to make half-written transfers very likely

proc = start_server(PORT)
with client(f"http://localhost:{PORT}") as api:
    _, bots = fresh_start(api, bots=20, start_balance=10_000)
kill_server(proc)

for round_ in range(ROUNDS):
    proc = start_server(PORT)
    with client(f"http://localhost:{PORT}") as api:
        jobs = [lambda i=i: transfer(api, bots[i % 10], bots[10 + i % 10], 1) for i in range(400)]
        threading.Timer(0.4, kill_server, args=(proc,)).start()  # pull the plug mid-run
        run_concurrently(jobs, workers=20)

report = money_report()
verdict("Problems 6-8 · crash partway through", {
    "completed transfers without 2 ledger lines (6)": report["completed_transfers_without_2_ledger_lines"],
    "accounts drifting from ledger (7, 8)": report["accounts_drifting_from_ledger"],
    "sum of all balances, must be 0 (8)": report["sum_of_all_balances"],
}, {"crashes": ROUNDS})
