# Bank Transfers

A money-transfer API we break on purpose, then fix one failure at a time.
Each step is a chaos script that reproduces a real bug, the fix, and the same script passing.

👉 **[See every step explained visually](https://claude.ai/artifact/PddBgGxBbkd1ZBXdY8KrpY#method)** — what breaks, why, and how we fixed it.

**Python 3.14 · FastAPI · Postgres 18 (Docker) · psycopg 3 + psycopg-pool, hand-written SQL · pytest**

## Where we are

| Step | What breaks | Fix | Proof |
| --- | --- | --- | --- |
| 0 · Happy path | – | the API itself | `scripts/00_basics.py` |
| 1 · Crash mid-transfer | half-written transfers | one transaction | `chaos/01_crash.py` ✅ |
| 2 · Concurrent transfers | lost updates, overdraft | `SELECT … FOR UPDATE` | `chaos/02_concurrency.py` ✅ |
| 3 · A→B and B→A at once | deadlocks | lock accounts by id order | `chaos/03_deadlock.py` ✅ |
| 4 · Two servers | per-process state, too many connections | locks in the DB, one pool per worker | `chaos/04_two_servers.py` ✅ |
| 5 · Client retries | duplicate transfers | idempotency key | `chaos/duplicate.py` 🚧 |
| 6 · Reconciliation | inconsistent reports | consistent snapshot | – |
| 7 · Notify a partner | lost or phantom events | outbox + worker | – |
| 8 · Two workers | events sent twice | `SKIP LOCKED` | – |

## Run it

```bash
python3 -m venv .venv && source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env

docker run -d --name wallet-db -e POSTGRES_USER=wallet -e POSTGRES_PASSWORD=wallet \
  -e POSTGRES_DB=wallet -p 5432:5432 postgres:18

python -m scripts.reset_db          # drop + recreate the tables
uvicorn app.main:app --reload       # http://localhost:8000/health
```

Then:

```bash
python -m scripts.00_basics         # the product end to end
python -m scripts.chaos.run_all     # every chaos script + a scoreboard (API on :8000)
pytest                              # validation tests
python -m scripts.live              # live view on http://localhost:8050
```

The live view starts its own servers and pushes real transfers through our API while showing
what Postgres sees: every worker, its pool connections, who waits for a lock, 503s, invariants.
It has one-click experiments for each step.

## API

All amounts are in cents.

| Route | Does |
| --- | --- |
| `GET /health` | checks the DB connection |
| `POST /accounts` `{owner}` | opens an account at 0 |
| `GET /accounts/{id}` | id, owner, balance |
| `POST /transfers` `{sender_id, receiver_id, amount}` | moves money, all or nothing |

Errors are `{"error": {"code", "message"}}`: `400` invalid_amount / same_account / invalid_owner,
`404` account_not_found, `409` owner_taken, `422` insufficient_funds (the refusal is still recorded),
`503` overloaded (no DB connection free within 5 s, retry later).

## How a transfer works

1. Lock both accounts with `SELECT … FOR UPDATE`, **lowest id first** (no deadlock).
2. Not enough money? Record a `refused` transfer, answer 422.
3. Otherwise insert the transfer, two ledger entries (−x, +x), and update both balances in SQL.
4. All of it in **one transaction**, on a connection borrowed from the worker's pool.

The `bank` account (`is_system`) is the only one allowed below 0: it funds everyone else.

## What must always be true

`tests/checker.py` checks it after every chaos script:

- all balances add up to 0: money is never created or lost
- each balance equals the sum of its ledger entries
- each completed transfer has exactly 2 entries that sum to 0
- refused transfers have no entries
- no regular account below 0

## Layout

```
app/            FastAPI app: routes/, services/ (the SQL), db.py (pool), errors.py
db/schema.sql   accounts, transfers, ledger_entries
scripts/        reset_db, seed, 00_basics, live view
scripts/chaos/  one script per step, run_all.py
tests/          checker.py (invariants), API validation tests
docs/decisions/ why we chose what we chose
```

## How we work

One branch per step. One person writes the chaos script while the other writes the fix.
Every PR is reviewed by the other, and whoever wrote a part explains it to the other.
