"""Problem 10 · Too many connections.

Each request opens a brand-new Postgres connection. Run the API with several worker
processes (as you would in production, or with two instances, roadmap step 4) and
fire many requests at once: together they open more connections than Postgres allows
(about 100 by default), and requests start failing.

Starts its OWN server on port 8002 with 8 workers.
Run:  python -m scripts.chaos.connections
PASS when: no request fails AND the peak number of open connections stays under
80% of Postgres's limit. On a fast laptop each connection lives only milliseconds,
so failures may not happen yet; the peak shows how close you are to the cliff.
Fix: a connection pool per worker, sized so all workers together stay under the limit.
"""
import threading

from app.db import connect
from scripts.chaos.common import (client, fresh_start, kill_server, run_concurrently, start_server,
                                  transfer, verdict)

PORT = 8002
WORKERS = 8        # uvicorn worker processes, each handles ~40 requests at once
REQUESTS = 1200
IN_FLIGHT = 250    # requests sent at the same time

peak, stop = 0, threading.Event()


def watch_connections():
    global peak
    with connect() as conn:
        conn.autocommit = True
        while not stop.is_set():
            n = conn.execute("SELECT COUNT(*) FROM pg_stat_activity WHERE datname = current_database()").fetchone()[0]
            peak = max(peak, n)


with connect() as conn:
    limit = int(conn.execute("SHOW max_connections").fetchone()[0])

proc = start_server(PORT, workers=WORKERS)
try:
    with client(f"http://localhost:{PORT}") as api:
        _, bots = fresh_start(api, bots=200, start_balance=10_000)
        jobs = [lambda i=i: transfer(api, bots[i % 100], bots[100 + i % 100], 1) for i in range(REQUESTS)]
        watcher = threading.Thread(target=watch_connections)
        watcher.start()
        results = run_concurrently(jobs, workers=IN_FLIGHT)
        stop.set()
        watcher.join()
finally:
    kill_server(proc)

failed = [r for r in results if isinstance(r, Exception) or r.status_code >= 500]
verdict("Problem 10 · too many connections", {
    "requests that failed (5xx or no answer)": len(failed),
    "connections above 80% of the limit": max(peak - int(limit * 0.8), 0),
}, {"requests": REQUESTS, "in flight at once": IN_FLIGHT, "API workers": WORKERS,
    "peak open connections": peak, "Postgres limit": limit})
