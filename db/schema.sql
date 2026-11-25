CREATE TABLE accounts (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    owner       TEXT        NOT NULL UNIQUE CHECK (owner <> ''),
    balance     BIGINT      NOT NULL DEFAULT 0,
    is_system   BOOLEAN     NOT NULL DEFAULT false,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    --CHECK       (balance >= 0 OR is_system)
);

CREATE TABLE transfers (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    --idempotency_key TEXT        NOT NULL UNIQUE,
    sender_id       BIGINT      NOT NULL REFERENCES accounts(id),
    receiver_id     BIGINT      NOT NULL REFERENCES accounts(id),
    amount          BIGINT      NOT NULL CHECK (amount > 0),
    status          TEXT        NOT NULL CHECK (status IN ('completed','refused')),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (sender_id <> receiver_id)
);

CREATE TABLE ledger_entries (
    id      BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    transfer_id BIGINT  NOT NULL REFERENCES transfers(id),
    account_id   BIGINT NOT NULL REFERENCES accounts(id),
    amount      BIGINT NOT NULL CHECK (amount <> 0),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (transfer_id, account_id)
);