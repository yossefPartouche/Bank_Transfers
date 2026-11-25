import os

import psycopg
from dotenv import load_dotenv

load_dotenv()                                # Load env var from .env file
DATABASE_URL = os.environ["DATABASE_URL"]    # Get the database URL from env var


def get_conn():                              # return a connection to the db
    return psycopg.connect(DATABASE_URL)