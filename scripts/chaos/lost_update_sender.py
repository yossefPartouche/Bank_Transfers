"""Problem 1 · Lost update on the sender.

One account sends many small transfers at the same time. Each request reads the
sender's balance, then writes its own result, so later writes erase earlier ones:
the sender is debited less than it paid, and money is created.

Run:  python -m scripts.chaos.lost_update_sender
PASS when: every balance matches its ledger and the money still sums to 0.
"""
from scripts.chaos.common import client, fresh_start, money_report, run_concurrently, transfer, verdict

TRANSFERS = 200
AMOUNT = 10

with client() as api:
    _, bots = fresh_start(api, bots=21, start_balance=10_000)
    sender, receivers = bots[0], bots[1:]
    jobs = [lambda i=i: transfer(api, sender, receivers[i % len(receivers)], AMOUNT) for i in range(TRANSFERS)]
    results = run_concurrently(jobs)
    ok = sum(1 for r in results if not isinstance(r, Exception) and r.status_code == 201)
    sender_balance = api.get(f"/accounts/{sender}").json()["balance"]

report = money_report()
expected = 10_000 - ok * AMOUNT
verdict("Problem 1 · lost update on the sender", {
    "sender balance minus what it should be": sender_balance - expected,
    "sum of all balances (must be 0)": report["sum_of_all_balances"],
    "accounts drifting from ledger": report["accounts_drifting_from_ledger"],
}, {"successful transfers": ok, "sender balance": sender_balance, "expected": expected})
