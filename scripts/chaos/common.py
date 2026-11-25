"""Shared helpers for the chaos scripts.

Every script: reset the DB, seed accounts through the API, attack, then check the money.
The API must be running (uvicorn app.main:app --port 8000), except for crash.py,
which starts and kills its own server.
"""
import os
import signal
import subprocess
import sys
import time
import uuid
from concurrent.futures import ThreadPoolExecutor

import httpx

from app.db import get_conn
from scripts.reset import reset

API_URL = os.environ.get("API_URL", "http://localhost:8000")


def client(base_url: str = API_URL) -> httpx.Client:
    return httpx.Client(base_url=base_url, timeout=30)


def fresh_start(api: httpx.Client, bots: int, start_balance: int) -> tuple[int, list[int]]:
    """Reset the DB, create the system account and `bots` accounts funded with `start_balance` each.

    Funding goes through POST /transfers from the system account, so the ledger is right from line one.
    Returns (system_id, [bot ids]).
    """
    reset()
    system_id = api.post("/accounts", json={"owner": "system"}).json()["id"]
    with get_conn() as conn:  # is_system can't be set through the API, on purpose
        conn.execute("UPDATE accounts SET is_system = true WHERE id = %s", (system_id,))
    ids = [api.post("/accounts", json={"owner": f"bot-{i}"}).json()["id"] for i in range(bots)]
    for bot in ids:
        if start_balance:
            r = api.post("/transfers", json={"sender_id": system_id, "receiver_id": bot, "amount": start_balance})
            r.raise_for_status()
    return system_id, ids


def transfer(api: httpx.Client, sender: int, receiver: int, amount: int, key: str | None = None) -> httpx.Response:
    headers = {"Idempotency-Key": key or str(uuid.uuid4())}
    return api.post("/transfers", json={"sender_id": sender, "receiver_id": receiver, "amount": amount}, headers=headers)


def run_concurrently(jobs, workers: int = 20) -> list:
    """Run a list of zero-argument functions at the same time; return their results (or exceptions)."""
    def safe(job):
        try:
            return job()
        except Exception as e:  # a failed request is a result too
            return e
    with ThreadPoolExecutor(workers) as pool:
        return list(pool.map(safe, jobs))


def start_server(port: int, workers: int = 1) -> subprocess.Popen:
    """Start our own API server (used by scripts that kill it or need several workers)."""
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
            except Exception:
                pass
            time.sleep(0.2)
    raise SystemExit("server didn't start")


def kill_server(proc: subprocess.Popen) -> None:
    """SIGKILL the whole server: no cleanup, no goodbye, like a power cut."""
    os.killpg(proc.pid, signal.SIGKILL)
    proc.wait()


def money_report() -> dict:
    """The referee: every number here should be 0 on a correct system."""
    with get_conn() as conn:
        q = lambda sql: conn.execute(sql).fetchone()[0]
        return {
            # system goes negative by what it gave out, so all balances together must sum to 0
            "sum_of_all_balances": q("SELECT COALESCE(SUM(balance), 0) FROM accounts"),
            # every completed transfer writes -x and +x, so the ledger must sum to 0
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


def verdict(name: str, problems: dict, details: dict | None = None) -> None:
    """Print PASS/FAIL. `problems` maps a label to a number that must be 0. Exit 1 on FAIL."""
    print(f"\n=== {name}")
    for k, v in (details or {}).items():
        print(f"  {k}: {v}")
    bad = {k: v for k, v in problems.items() if v}
    for k, v in problems.items():
        print(f"  {'FAIL' if v else 'ok  '} {k}: {v}")
    print("RESULT:", "FAIL (bug reproduced)" if bad else "PASS")
    sys.exit(1 if bad else 0)
