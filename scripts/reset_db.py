from pathlib import Path

from app.db import connect

DB_DIR = Path(__file__).resolve().parent.parent / "db"
FILES = ["schema.sql"]


def reset_db():
    with connect() as conn:         # open a connection to the db
        for name in FILES:           # read and send each file in the FILES list to the db
            sql = (DB_DIR / name).read_text()
            conn.execute(sql)
    print("Database reset: schema applied")


if __name__ == "__main__":
    reset_db()