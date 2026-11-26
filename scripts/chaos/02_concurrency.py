"""Step 2 · Concurrent transfers on the same account.

Each transfer reads a balance, computes the new value in Python, and writes it back.
When several transfers touch the SAME account at the same moment, they all read the
same old balance and overwrite each other's result.

Scenario A · lost update, sender: one account sends many transfers at once, each to a
DIFFERENT receiver (so the sender is the only shared account).

Scenario B · lost update, receiver: many DIFFERENT accounts pay the same receiver at
once, each exactly once (so the receiver is the only shared account).

Scenario C · overdraft: an account that can afford ONE transfer fires many at once, each
to a different receiver. Every request checks the balance before any has written, so
several pass the check: too many succeed and money is created (or the balance goes below 0).

Ensuring Problem Isoluation:
NO DEADLOCK: Money only flows one way (no A→B and B→A at once)
NO RETRY: every request has its own idempotency key, so retries can't be the cause either.

Run:   python -m scripts.chaos.02_concurrency      (needs the API on API_URL, default port 8000)
PASS:  A · the sender's balance = start - (successful transfers × amount), in every round
       B · the receiver's balance = start + (successful transfers × amount), in every round
       C · exactly 1 success, all the others refused (422), balance = start - amount
"""

from scripts.chaos.common import all_at_once, client, fresh_start, verdict
from tests.checker import check

ROUNDS = 3  # lost updates depend on timing: a PASS must hold every time, not once by luck

# Scenario A
A_START = 10_000   # the sender starts with 100.00
A_SENDS = 200      # transfers fired at the same moment
A_AMOUNT = 10      # 0.10 each

# Scenario B
B_START = 1_000    # every account starts with 10.00
B_SENDERS = 100    # accounts paying the receiver at the same moment
B_AMOUNT = 10      # 0.10 each

# Scenario C
C_START = 100      # the spender holds 1.00
C_TRIES = 20       # transfers fired at the same moment
C_AMOUNT = 80      # 0.80 each: affordable exactly once


def lost_update_sender(api):
    """Scenario A, one round. Returns a dict of numbers for the verdict."""
    _, (sender, *receivers) = fresh_start(bots=1 + A_SENDS, start_balance=A_START)
    codes = all_at_once(api, [(sender, r, A_AMOUNT) for r in receivers])

    # This is the number of threads which actually got through to the DB
    ok = codes.count(201)
    balance = api.get(f"/accounts/{sender}").json()["balance"]
    expected = A_START - ok * A_AMOUNT
    return {
        "succeeded": ok,
        "not 201 (should be 0: the sender can afford all)": len(codes) - ok,
        "balance": balance,
        "expected": expected,
        "broken invariants": [name for name, _ in check()],
    }

def lost_update_receiver(api):
    """Scenario B, one round. Returns a dict of numbers for the verdict."""
    _, (receiver, *senders) = fresh_start(bots=1 + B_SENDERS, start_balance=B_START)
    codes = all_at_once(api, [(s, receiver, B_AMOUNT) for s in senders])

    ok = codes.count(201)
    balance = api.get(f"/accounts/{receiver}").json()["balance"]
    expected = B_START + ok * B_AMOUNT
    return {
        "succeeded": ok,
        "not 201": len(codes) - ok,  # every sender can afford its one transfer
        "balance": balance,
        "expected": expected,
        "broken invariants": [name for name, _ in check()],
    }

def overdraft(api):
    """Scenario C, one round. Returns a dict of numbers for the verdict."""
    _, (spender, *receivers) = fresh_start(bots=1 + C_TRIES, start_balance=C_START)
    codes = all_at_once(api, [(spender, r, C_AMOUNT) for r in receivers])

    return {
        "succeeded": codes.count(201),
        "refused": codes.count(422),
        "other": len(codes) - codes.count(201) - codes.count(422),  # 500s, no answer...
        "balance": api.get(f"/accounts/{spender}").json()["balance"],
        "broken invariants": [name for name, _ in check()],
    }


if __name__ == "__main__":
    with client() as api:
        a = [lost_update_sender(api) for _ in range(ROUNDS)]
        b = [lost_update_receiver(api) for _ in range(ROUNDS)]
        c = [overdraft(api) for _ in range(ROUNDS)]

    verdict("Step 2 · concurrent transfers", {
        "A · rounds where the sender's balance is wrong": sum(r["balance"] != r["expected"] for r in a),
        "A · rounds with unexpected answers (not 201)": sum(r["not 201 (should be 0: the sender can afford all)"] > 0 for r in a),
        "A · rounds with broken invariants": sum(bool(r["broken invariants"]) for r in a),
        "B · rounds where the receiver's balance is wrong": sum(r["balance"] != r["expected"] for r in b),
        "B · rounds with unexpected answers (not 201)": sum(r["not 201"] > 0 for r in b),
        "B · rounds with broken invariants": sum(bool(r["broken invariants"]) for r in b),
        "C · rounds with more than 1 success": sum(r["succeeded"] > 1 for r in c),
        "C · rounds with answers other than 201/422": sum(r["other"] > 0 for r in c),
        "C · rounds with a wrong final balance": sum(r["balance"] != C_START - C_AMOUNT for r in c),
        "C · rounds with broken invariants": sum(bool(r["broken invariants"]) for r in c),
    }, details={
        "rounds": ROUNDS,
        "A · (balance, expected), per round": ", ".join(f"({r['balance']} vs {r['expected']})" for r in a),
        "A · invariants broken (last round)": ", ".join(a[-1]["broken invariants"]) or "none",
        "B · (balance, expected), per round": ", ".join(f"({r['balance']} vs {r['expected']})" for r in b),
        "B · invariants broken (last round)": ", ".join(b[-1]["broken invariants"]) or "none",
        "C · (succeeded, refused, other) per round": ", ".join(f"({r['succeeded']},{r['refused']},{r['other']})" for r in c),
        "C · final balance, per round (expected 20)": ", ".join(str(r["balance"]) for r in c),
        "C · invariants broken (last round)": ", ".join(c[-1]["broken invariants"]) or "none",
    }, invariants=False)  # each round ran the checker itself; the DB is reset between rounds