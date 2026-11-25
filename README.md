# Bank Transfers

A money-transfer API built to break, then fixed one problem at a time: crashes, double spending, deadlocks, retries, and notifying a partner without losing or duplicating events.

**Invariant:** money is never created or lost. The sum of all balances is always 0 (the bank account holds the negative side).

## Stack

Python · FastAPI · Postgres 18 (Docker) · psycopg 3 with hand-written SQL · pytest

## Setup

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env

docker run -d --name wallet-db \
  -e POSTGRES_USER=wallet -e POSTGRES_PASSWORD=wallet -e POSTGRES_DB=wallet \
  -p 5432:5432 postgres:18

python scripts/reset.py              # schema + seed
uvicorn app.main:app --reload        # http://localhost:8000/docs
```

## Layout

```
app/       API (routes) and business logic (transfers, SQL)
db/        schema.sql, seed.sql
scripts/   reset.py, one script per step (00_basics, 01_crash, …)
tests/     pytest, shared checker
```

## Contract

**Database:** `DATABASE_URL=postgresql://wallet:wallet@localhost:5432/wallet`

- `accounts(id, name, balance_cents BIGINT)`: id 1 is the bank, the only account allowed below 0
- `transfers(id, from_id, to_id, amount_cents, created_at)`

**API:**

| Route | Body | Response |
| --- | --- | --- |
| `POST /accounts` | `{name, initial_cents}` | `{id, balance_cents}` |
| `GET /accounts/{id}` | — | `{id, balance_cents}` |
| `POST /transfers` | `{from_id, to_id, amount_cents}` | `201 {id, …}` |

Errors: `422` invalid input · `404` unknown account · `409` insufficient funds. `Idempotency-Key` header is reserved for step 5.

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