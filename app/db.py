import sqlite3
import time
from contextlib import contextmanager
from .config import DB_PATH


@contextmanager
def conn():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    try:
        yield c
        c.commit()
    finally:
        c.close()


def init():
    with conn() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS users(
            id INTEGER PRIMARY KEY,
            name TEXT,
            balance REAL DEFAULT 0,
            level INTEGER DEFAULT 0,
            last_claim REAL,
            referrer INTEGER,
            last_daily REAL DEFAULT 0,
            channel_done INTEGER DEFAULT 0,
            created REAL
        );
        """)


def get_or_create(uid: int, name: str = "", referrer: int | None = None):
    with conn() as c:
        row = c.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
        if row:
            return dict(row), False
        if referrer == uid or not (referrer and c.execute(
                "SELECT 1 FROM users WHERE id=?", (referrer,)).fetchone()):
            referrer = None
        now = time.time()
        c.execute("INSERT INTO users(id,name,last_claim,referrer,created) VALUES(?,?,?,?,?)",
                  (uid, name, now, referrer, now))
        return dict(c.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()), True


def update(uid: int, **fields):
    keys = ", ".join(f"{k}=?" for k in fields)
    with conn() as c:
        c.execute(f"UPDATE users SET {keys} WHERE id=?", (*fields.values(), uid))


def add_balance(uid: int, amount: float):
    with conn() as c:
        c.execute("UPDATE users SET balance=balance+? WHERE id=?", (amount, uid))


def friends(uid: int):
    with conn() as c:
        return [dict(r) for r in c.execute(
            "SELECT id,name,level FROM users WHERE referrer=? ORDER BY created DESC", (uid,))]
