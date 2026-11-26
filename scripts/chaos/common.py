"""Shared helpers for the chaos scripts.

Every script follows the same pattern:
    1. fresh_start()   clean DB + accounts funded by the bank (direct SQL, no API)
    2. attack through the API with transfer() and run_concurrently()
    3. verdict()       the script's own numbers + the shared invariant checker

The API must be running on API_URL (default http://localhost:8000),
except for scripts that start their own server with start_server().
"""
import contextlib
import io
import os
import signal
import subprocess
import sys
import time
import uuid
from concurrent.futures import ThreadPoolExecutor

import httpx

from app.db import get_conn
from scripts.reset_db import reset_db
from scripts.seed import seed
from tests.checker import check
from tests.checker import CHECKS, check

API_URL = os.environ.get("API_URL", "http://localhost:8000")


# ---------- setup ----------

def client(base_url=API_URL):
    return httpx.Client(base_url=base_url, timeout=30)


def fresh_start(api=None, bots=2, start_balance=10_000):
    """Clean DB, then `bots` accounts funded by the bank. Returns (bank_id, [bot ids]).

    Uses SQL, not the API: the starting state must not depend on the code under test.
    `api` is unused, kept so the older scripts still run unchanged.
    """
    assert start_balance > 0, "a funding transfer must be positive"
    names = [f"bot-{i}" for i in range(bots)]
    with contextlib.redirect_stdout(io.StringIO()):  # reset/seed print; keep the output readable
        reset_db()
        ids = seed({name: start_balance for name in names})
    return ids["bank"], [ids[name] for name in names]


# ---------- attack ----------

def transfer(api, sender, receiver, amount, key=None):
    """POST /transfers, always with an Idempotency-Key (random unless given)."""
    headers = {"Idempotency-Key": key or str(uuid.uuid4())}
    body = {"sender_id": sender, "receiver_id": receiver, "amount": amount}
    return api.post("/transfers", json=body, headers=headers)


def run_concurrently(jobs, workers=20):
    """Run zero-argument functions at the same time. Returns results; a failed call returns its exception."""
    def safe(job):
        try:
            return job()
        except Exception as e:
            return e
    with ThreadPoolExecutor(workers) as pool:
        return list(pool.map(safe, jobs))


def start_server(port, workers=1):
    """Start our own API server (for scripts that kill it or need several workers)."""
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(port),
         "--workers", str(workers), "--log-level", "warning"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True,
    )
    with client(f"http://localhost:{port}") as c:
        for _ in range(100):
            try:
                if c.get("/health").status_code == 200:
                    return proc
            except httpx.HTTPError:
                pass
            time.sleep(0.2)
    raise SystemExit(f"server on port {port} didn't start")


def kill_server(proc):
    """SIGKILL the whole server: no cleanup, like a power cut."""
    os.killpg(proc.pid, signal.SIGKILL)
    proc.wait()


# ---------- judge ----------

def money_report():
    """Old referee, kept until each script is rewritten (01_crash, 02_concurrency, ...).
    New scripts rely on verdict(), which runs tests/checker.py."""
    with get_conn() as conn:
        q = lambda sql: conn.execute(sql).fetchone()[0]
        return {
            "sum_of_all_balances": q("SELECT COALESCE(SUM(balance), 0) FROM accounts"),
            "sum_of_ledger": q("SELECT COALESCE(SUM(amount), 0) FROM ledger_entries"),
            "accounts_drifting_from_ledger": q("""
                SELECT COUNT(*) FROM accounts a
                WHERE a.balance <> COALESCE((SELECT SUM(amount) FROM ledger_entries l
                                             WHERE l.account_id = a.id), 0)"""),
            "negative_balances": q("SELECT COUNT(*) FROM accounts WHERE balance < 0 AND NOT is_system"),
            "completed_transfers_without_2_ledger_lines": q("""
                SELECT COUNT(*) FROM transfers t
                WHERE t.status = 'completed'
                  AND (SELECT COUNT(*) FROM ledger_entries l WHERE l.transfer_id = t.id) <> 2"""),
        }


def verdict(name, problems, details=None, invariants=True):
    """Print a readable report, then exit 0 (PASS) or 1 (FAIL) for run_all."""
    print(f"\n━━ {name} " + "━" * max(3, 60 - len(name)))
    for label, value in (details or {}).items():
        print(f"    {label:<40} {value}")

    failed = False
    print()
    for label, value in problems.items():
        print(f"  {'✗' if value else '✓'} {label:<40} {value}")
        failed |= bool(value)

    if invariants:
        broken = dict(check())
        print("\n  invariants (tests/checker.py)")
        for rule in CHECKS:
            n = len(broken.get(rule, []))
            print(f"  {'✗' if n else '✓'} {rule:<40} {n or ''}")
        failed |= bool(broken)

    print("\n  " + ("FAIL · bug reproduced" if failed else "PASS"))
    sys.exit(1 if failed else 0)