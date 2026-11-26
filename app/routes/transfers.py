from fastapi import APIRouter, Header

from app.schemas import TransferIn
from app.services import transfers

router = APIRouter()

# pydantic will verify the request body against the TransferIn schema (in schemas.py) and convert it to a TransferIn object
@router.post("/transfers", status_code=201)
def create_transfer(body: TransferIn, idempotency_key: str |None = Header(default=None)):
    return transfers.transfer(body.sender_id, body.receiver_id, body.amount, idempotency_key)