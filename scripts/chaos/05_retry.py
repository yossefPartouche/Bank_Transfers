"""Step 5 · Retries and duplicate requests.

A client can't always tell whether its transfer went through: the reply may be lost
(timeout, network drop) even though the server committed. The safe reaction is to send
the SAME request again, with the SAME Idempotency-Key. The server must recognise it and
answer as the first time, without moving the money a second time.

Scenario A · lost reply, client resends: one transfer, then the identical request again,
same key, one after the other (as a client retrying after a timeout would).

Scenario B · double click: the identical request twice at the SAME instant, same key (a user
tapping "Pay" twice, or an app sending twice). Both arrive before either has finished, so a
"have I seen this key?" check alone isn't enough: both can see "no" and both transfer.

Isolation: steps 1-4 are fixed, both accounts are rich (no refusal), one client only (no
lost update, no deadlock). The only way money can move twice is a duplicate request.
The checker can't see this bug (the books balance): we count transfers per key instead.

Run:   python -m scripts.chaos.05_retry      (needs the API on API_URL, default port 8000)
Fix:   store the Idempotency-Key with the transfer (UNIQUE, same transaction); a known key
       returns the stored answer instead of transferring again
PASS:  A · 1 transfer, the money moved once, both answers identical (status and transfer id)
       B · same, in every round
"""
from app.db import connect
from scripts.chaos.common import client, fresh_start, transfer, verdict, fire_at_once

START = 100_000    # 1,000.00 each: nobody can run out of money
AMOUNT = 5_000     # 50.00
ROUNDS = 5         # double click is a time race a PASS must hold every time


def completed_transfers(sender, receiver):
    """How many completed transfers the database holds between these two accounts."""
    with connect() as conn:
        return conn.execute(
            "SELECT count(*) FROM transfers WHERE sender_id = %s AND receiver_id = %s AND status = 'completed'",
            (sender, receiver),
        ).fetchone()[0]


def answer(response):
    """What the client sees: (status code, transfer id). Same key → must be identical."""
    body = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
    return response.status_code, body.get("id")


# ---------- scenario A ----------

def lost_reply_resend(api):
    """Scenario A. The client sends, 'loses' the reply, and sends the same request again."""
    _, (a, b) = fresh_start(bots=2, start_balance=START)
    first = transfer(api, a, b, AMOUNT, key="retry-A")
    second = transfer(api, a, b, AMOUNT, key="retry-A")   # same key: it's the same intended transfer

    return {
        "transfers": completed_transfers(a, b),
        "receiver gained": api.get(f"/accounts/{b}").json()["balance"] - START,
        "first answer": answer(first),
        "second answer": answer(second),
    }

# ----------- scenario B ----------

def double_click(api, round_no):
    """Scenario B, one round. Two identical requests, same key, at the same instant."""
    _, (a, b) = fresh_start(bots=2, start_balance=START)
    key = f"double-click-{round_no}"
    codes = fire_at_once(api, [(a, b, AMOUNT, key)] * 2)

    return {
        "transfers": completed_transfers(a, b),
        "receiver gained": api.get(f"/accounts/{b}").json()["balance"] - START,
        "codes": codes,
    } 


if __name__ == "__main__":
    with client() as api:
        a = lost_reply_resend(api)
        b = [double_click(api, n) for n in range(ROUNDS)]

    verdict("Step 5 · retries and duplicates", {
        "A · extra transfers (should be 1 in total)": a["transfers"] - 1,
        "A · money moved more than once": int(a["receiver gained"] != AMOUNT),
        "A · second answer differs from the first": int(a["first answer"] != a["second answer"]),
        "B · rounds with more than 1 transfer": sum(r["transfers"] > 1 for r in b),
        "B · rounds where the money moved more than once": sum(r["receiver gained"] != AMOUNT for r in b),
        "B · rounds where the two answers differ": sum(len(set(r["codes"])) > 1 for r in b),
    }, details={
        "A · transfers in the database": a["transfers"],
        "A · receiver gained (expected 5000)": a["receiver gained"],
        "A · first answer (status, id)": a["first answer"],
        "A · second answer (status, id)": a["second answer"],
        "B · rounds": ROUNDS,
        "B · transfers per round": ", ".join(str(r["transfers"]) for r in b),
        "B · answers per round": ", ".join(str(r["codes"]) for r in b),
    }, invariants=False)  # the books balance even with a duplicate: the checker can't see this bug