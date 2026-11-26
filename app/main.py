from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from psycopg_pool import PoolTimeout

from app import errors
from app.db import pool
from app.routes import accounts, health, transfers


@asynccontextmanager
async def lifespan(app):
    pool.open(wait=True)  # startup: open this worker's connections (fails now if the DB is down)
    yield                 # the API serves requests here
    pool.close()          # shutdown: close them cleanly


app = FastAPI(lifespan=lifespan)  # the pool is opened once per worker, not per request
app.include_router(health.router)
app.include_router(accounts.router)
app.include_router(transfers.router)


# Business error -> (HTTP status, error code). The only place that knows both worlds.
HTTP_ERRORS = {
    errors.AccountNotFound: (404, "account_not_found"),
    errors.InsufficientFunds: (422, "insufficient_funds"),
    errors.InvalidAmount: (400, "invalid_amount"),
    errors.SameAccount: (400, "same_account"),
    errors.InvalidOwner: (400, "invalid_owner"),
    errors.OwnerTaken: (409, "owner_taken"),
    PoolTimeout: (503, "overloaded"),  # no free connection within POOL_TIMEOUT: retry later
}


def make_handler(status, code):
    def handler(request, exc):
        return JSONResponse(status_code=status, content={"error": {"code": code, "message": str(exc)}})
    return handler


for exc_class, (status, code) in HTTP_ERRORS.items():
    app.add_exception_handler(exc_class, make_handler(status, code))