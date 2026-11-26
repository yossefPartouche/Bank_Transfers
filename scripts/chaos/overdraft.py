"""Problems 3 and 4 · Overdraft (double spending) and decisions on stale data.

An account holds 100 and fires 20 transfers of 80 at the same time. Only ONE can
succeed. Each request checks "100 >= 80" on a balance that's already out of date,
so several pass: the account goes negative and money is created.
(Problem 4, wrong decisions on stale reads, has the same root cause and the same fix.)

Run:  python -m scripts.chaos.overdraft
PASS when: exactly 1 transfer succeeds, 19 are refused, and nothing goes negative.
"""
from scripts.chaos.common import client, fresh_start, money_report, run_concurrently, transfer, verdict

ATTEMPTS = 20

with client() as api:
    _, bots = fresh_start(api, bots=ATTEMPTS + 1, start_balance=100)
    spender, receivers = bots[0], bots[1:]
    results = run_concurrently([lambda r=r: transfer(api, spender, r, 80) for r in receivers], workers=ATTEMPTS)
    codes = [r.status_code if not isinstance(r, Exception) else "error" for r in results]
    spender_balance = api.get(f"/accounts/{spender}").json()["balance"]

ok = codes.count(201)
report = money_report()
verdict("Problems 3 + 4 · overdraft on stale balance", {
    "extra transfers that should have been refused": max(ok - 1, 0),
    "negative balances": report["negative_balances"],
    "sum of all balances (must be 0)": report["sum_of_all_balances"],
}, {"succeeded": ok, "refused (422)": codes.count(422), "spender balance": spender_balance})
