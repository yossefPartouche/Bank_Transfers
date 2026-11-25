from fastapi import APIRouter

from app.schemas import AccountIn
from app.services import accounts

router = APIRouter()


@router.post("/accounts", status_code=201)
def create_account(body: AccountIn):
    return accounts.create_account(body.owner)


@router.get("/accounts/{account_id}")
def get_account(account_id: int):
    return accounts.get_account(account_id)