"""Step 0 · Happy path: the whole product works end to end, through the API."""
import httpx
import uuid
from scripts.reset_db import reset_db
from scripts.seed import seed
from tests.checker import check

API = "http://localhost:8000"


def eur(cents):
    return f"{cents / 100:.2f} €"


def step(label, resp, expected):
    """Check the HTTP status, print one readable line, return the JSON body."""
    ok = resp.status_code == expected
    print(f"  {'✓' if ok else '✗'} {label:<38} → {resp.status_code} (expected {expected})")
    assert ok, resp.text
    return resp.json()


def transfer(api, sender, receiver, amount):
    return api.post("/transfers", json={"sender_id": sender, "receiver_id": receiver, "amount": amount}, headers={"Idempotency-Key": str(uuid.uuid4())})


def main():
    try:
        httpx.get(f"{API}/health")
    except httpx.ConnectError:
        raise SystemExit(f"✗ API not reachable at {API}: start it with `uvicorn app.main:app --reload`")

    print("1. Clean database, bank only")
    reset_db()
    ...
    bank = seed({})["bank"]

    with httpx.Client(base_url=API) as api:
        print("2. Open accounts")
        a = step("create A", api.post("/accounts", json={"owner": "A"}), 201)["id"]
        b = step("create B", api.post("/accounts", json={"owner": "B"}), 201)["id"]

        print("3. Fund them from the bank")
        step(f"bank → A  {eur(10000)}", transfer(api, bank, a, 10000), 201)
        step(f"bank → B  {eur(10000)}", transfer(api, bank, b, 10000), 201)

        print("4. Normal transfers")
        step(f"A → B  {eur(3000)}", transfer(api, a, b, 3000), 201)
        step(f"B → A  {eur(1000)}", transfer(api, b, a, 1000), 201)

        print("5. Transfers that must be refused")
        step(f"A → B  {eur(50000)} (insufficient funds)", transfer(api, a, b, 50000), 422)
        step("A → B  0 (invalid amount)", transfer(api, a, b, 0), 400)
        step("A → A  (same account)", transfer(api, a, a, 100), 400)
        step("A → 999  (unknown account)", transfer(api, a, 999, 100), 404)

        print("6. Final balances")
        for name, acc, expected in [("A", a, 8000), ("B", b, 12000)]:
            balance = step(f"read {name}", api.get(f"/accounts/{acc}"), 200)["balance"]
            print(f"      {name}: {eur(balance)} (expected {eur(expected)})")
            assert balance == expected

    print("7. Invariants")
    problems = check()
    for name, rows in problems:
        print(f"  ✗ {name}: {rows}")
    assert not problems
    print("  ✓ all invariants hold")

    print("\n✓ 00_basics passed")


if __name__ == "__main__":
    main()