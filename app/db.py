# app/db.py 
# the only way to connect to the database is through this module, which reads the DATABASE_URL from the .env file and returns a connection object
import os

import psycopg
from dotenv import load_dotenv

load_dotenv()                                # Load env var from .env file
DATABASE_URL = os.environ["DATABASE_URL"]    # Get the database URL from env var


def get_conn(autocommit=False):
    return psycopg.connect(DATABASE_URL, autocommit=autocommit)