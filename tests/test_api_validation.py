from fastapi.testclient import TestClient

import pytest

from app.main import app
from scripts.reset_db import reset_db
from scripts.seed import seed
from tests.checker import check

client = TestClient(app)


@pytest.fixture
def ids():
    """Fresh database before each test: bank + A and B with 100 € each."""
    reset_db()
    return seed({"A": 10000, "B": 10000})


def transfer(sender, receiver, amount):
    return client.post("/transfers", json={"sender_id": sender, "receiver_id": receiver, "amount": amount})


def test_unknown_sender(ids):
    assert transfer(999, ids["B"], 100).status_code == 404


def test_negative_amount(ids):
    assert transfer(ids["A"], ids["B"], -100).status_code == 400


def test_get_unknown_account(ids):
    assert client.get("/accounts/999").status_code == 404


def test_duplicate_owner(ids):
    assert client.post("/accounts", json={"owner": "A"}).status_code == 409


def test_empty_owner(ids):
    assert client.post("/accounts", json={"owner": ""}).status_code == 400


def test_missing_field(ids):
    resp = client.post("/transfers", json={"sender_id": ids["A"], "receiver_id": ids["B"]})
    assert resp.status_code == 422


def test_amount_not_a_number(ids):
    assert transfer(ids["A"], ids["B"], "abc").status_code == 422


def test_decimal_amount(ids):
    assert transfer(ids["A"], ids["B"], 10.5).status_code == 422


def test_refused_transfer_changes_nothing(ids):
    assert transfer(ids["A"], ids["B"], 50000).status_code == 422
    assert client.get(f"/accounts/{ids['A']}").json()["balance"] == 10000
    assert client.get(f"/accounts/{ids['B']}").json()["balance"] == 10000
    assert check() == []