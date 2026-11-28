from fastapi import APIRouter, Header

from app.errors import MissingIdempotencyKey
from app.schemas import TransferIn
from app.services import transfers

router = APIRouter()

# pydantic will verify the request body against the TransferIn schema (in schemas.py) and convert it to a TransferIn object
@router.post("/transfers", status_code=201)
def create_transfer(body: TransferIn, idempotency_key: str |None = Header(default=None)):
    if not idempotency_key:
        raise MissingIdempotencyKey("provide a valid idempotency-Key header")
    return transfers.transfer(body.sender_id, body.receiver_id, body.amount, idempotency_key)