from app.db import get_conn

CHECKS = {
    "total is not 0 (money created or lost)":
        "SELECT sum(balance) FROM accounts HAVING sum(balance) <> 0",

    "balance differs from its ledger (drift)":
        """SELECT a.owner, a.balance, coalesce(sum(l.amount), 0)
           FROM accounts a LEFT JOIN ledger_entries l ON l.account_id = a.id
           GROUP BY a.id
           HAVING a.balance <> coalesce(sum(l.amount), 0)""",

    "completed transfer without exactly 2 entries summing to 0":
        """SELECT t.id, count(l.id), coalesce(sum(l.amount), 0)
           FROM transfers t LEFT JOIN ledger_entries l ON l.transfer_id = t.id
           WHERE t.status = 'completed'
           GROUP BY t.id
           HAVING count(l.id) <> 2 OR coalesce(sum(l.amount), 0) <> 0""",

    "refused transfer with ledger entries":
        """SELECT t.id FROM transfers t JOIN ledger_entries l ON l.transfer_id = t.id
           WHERE t.status = 'refused'""",

    "regular account below 0 (double spend)":
        "SELECT owner, balance FROM accounts WHERE balance < 0 AND NOT is_system",
}


def check():
    violations = []
    with get_conn() as conn:
        for name, sql in CHECKS.items():
            rows = conn.execute(sql).fetchall()
            if rows:
                violations.append((name, rows))
    return violations


if __name__ == "__main__":
    problems = check()
    if not problems:
        print("✓ all invariants hold")
    for name, rows in problems:
        print(f"✗ {name}: {rows}")