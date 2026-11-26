# app/db.py
# Two ways to reach the database:
#   get_conn()  the API's way: a connection borrowed from this process's pool
#   connect()   a dedicated connection, for scripts and tests (reset, seed, checker, chaos)
import os

import psycopg
from dotenv import load_dotenv
from psycopg_pool import ConnectionPool

load_dotenv()                                # Load env var from .env file
DATABASE_URL = os.environ["DATABASE_URL"]    # Get the database URL from env var

# One pool per API process. Budget: servers × workers × POOL_MAX < Postgres max_connections.
POOL_MAX = int(os.environ.get("DB_POOL_MAX", 10))
POOL_TIMEOUT = 5  # seconds a request waits for a free connection, then 503

pool = ConnectionPool(DATABASE_URL, min_size=2, max_size=POOL_MAX, timeout=POOL_TIMEOUT,
                      open=False)  # opened at startup by main.py


def get_conn():
    """Borrow a connection: commit (rollback on error) at the end of `with`, then give it back."""
    return pool.connection()


def connect(autocommit=False):
    """Open a dedicated connection, closed at the end of `with`. Scripts and tests only."""
    return psycopg.connect(DATABASE_URL, autocommit=autocommit)