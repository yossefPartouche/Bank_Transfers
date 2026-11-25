# Bank Transfers

A money-transfer API built to break, then fixed one problem at a time: crashes, double spending, deadlocks, retries, and notifying a partner without losing or duplicating events.

## Stack

Python 3.14 · FastAPI · Postgres 18 (Docker) · psycopg 3 with hand-written SQL · pytest

## Setup

```bash
python3 -m venv .venv && source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env

docker run -d --name wallet-db \
  -e POSTGRES_USER=wallet -e POSTGRES_PASSWORD=wallet -e POSTGRES_DB=wallet \
  -p 5432:5432 postgres:18

python -m scripts.reset              # drop + recreate tables
uvicorn app.main:app --reload        # http://localhost:8000/health
```

## Layout

```
app/       FastAPI app (main.py) and DB connection (db.py)
db/        schema.sql
scripts/   reset.py
tests/     (coming)
```

## Database

`DATABASE_URL=postgresql://wallet:wallet@localhost:5432/wallet` · all amounts in cents · see `db/schema.sql`

- `accounts(id, owner, balance, is_system, created_at)`: `is_system` marks the bank, the only account meant to go below 0. The `CHECK (balance >= 0)` is off on purpose until step 2.
- `transfers(id, sender_id, receiver_id, amount, status, created_at)`: `status` is `completed` or `refused`. `idempotency_key` is commented out until step 5.
- `ledger_entries(id, transfer_id, account_id, amount, created_at)`: one entry per account touched by a transfer.

## API

| Route | Status |
| --- | --- |
| `GET /health` | done: checks the DB connection |
| `POST /accounts`, `GET /accounts/{id}`, `POST /transfers` | to define |

## Roadmap

Each step: a script that breaks the system, the fix, the same script passing.

- [ ] 0 · Happy path
- [ ] 1 · Crash in the middle → transaction
- [ ] 2 · Double spending → DB lock
- [ ] 3 · Deadlock → lock ordering
- [ ] 4 · Two API instances → stateless API
- [ ] 5 · Client retries → idempotency key
- [ ] 6 · Reconciliation → consistent snapshot
- [ ] 7 · Notify a partner → outbox + worker
- [ ] 8 · Two workers → `SKIP LOCKED`

## How we work

One branch per task, every PR reviewed by the other. Whoever builds a part explains it to the other.