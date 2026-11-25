# app/schemas.py
# pydantic schemas for request bodies
from pydantic import BaseModel


class AccountIn(BaseModel):
    owner: str


class TransferIn(BaseModel):
    sender_id: int
    receiver_id: int
    amount: int