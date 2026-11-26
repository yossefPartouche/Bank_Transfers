"""Problem 2 · Lost update on the receiver.

Many DIFFERENT senders pay the same receiver at the same time. Each request reads
the receiver's balance and writes its own result, so credits get erased and money
disappears, even though no sender is shared.

Run:  python -m scripts.chaos.lost_update_receiver
PASS when: the receiver got every credit and the money still sums to 0.
"""
from scripts.chaos.common import client, fresh_start, money_report, run_concurrently, transfer, verdict

SENDERS = 100
AMOUNT = 10

with client() as api:
    _, bots = fresh_start(api, bots=SENDERS + 1, start_balance=1_000)
    receiver, senders = bots[0], bots[1:]
    results = run_concurrently([lambda s=s: transfer(api, s, receiver, AMOUNT) for s in senders])
    ok = sum(1 for r in results if not isinstance(r, Exception) and r.status_code == 201)
    receiver_balance = api.get(f"/accounts/{receiver}").json()["balance"]

report = money_report()
expected = 1_000 + ok * AMOUNT
verdict("Problem 2 · lost update on the receiver", {
    "receiver balance minus what it should be": receiver_balance - expected,
    "sum of all balances (must be 0)": report["sum_of_all_balances"],
    "accounts drifting from ledger": report["accounts_drifting_from_ledger"],
}, {"successful transfers": ok, "receiver balance": receiver_balance, "expected": expected})
