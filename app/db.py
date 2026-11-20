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
        CREATE TABLE IF NOT EXISTS payments(
            charge_id TEXT PRIMARY KEY,
            user_id INTEGER,
            item TEXT,
            stars INTEGER,
            created REAL,
            refunded INTEGER DEFAULT 0
        );
        """)
        cols = {r["name"] for r in c.execute("PRAGMA table_info(users)")}
        for col, ddl in [("username", "TEXT"), ("boost_mult", "REAL DEFAULT 1"),
                         ("boost_until", "REAL DEFAULT 0"), ("banned", "INTEGER DEFAULT 0")]:
            if col not in cols:
                c.execute(f"ALTER TABLE users ADD COLUMN {col} {ddl}")


def get(uid: int):
    with conn() as c:
        r = c.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
        return dict(r) if r else None


def get_or_create(uid: int, name: str = "", referrer: int | None = None, username: str | None = None):
    with conn() as c:
        row = c.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
        if row:
            if username is not None and (row["username"] != username or row["name"] != name):
                c.execute("UPDATE users SET username=?, name=? WHERE id=?", (username, name, uid))
                row = c.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
            return dict(row), False
        if referrer == uid or not (referrer and c.execute(
                "SELECT 1 FROM users WHERE id=?", (referrer,)).fetchone()):
            referrer = None
        now = time.time()
        c.execute("INSERT INTO users(id,name,username,last_claim,referrer,created) VALUES(?,?,?,?,?,?)",
                  (uid, name, username, now, referrer, now))
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


def friend_count(uid: int) -> int:
    with conn() as c:
        return c.execute("SELECT COUNT(*) FROM users WHERE referrer=?", (uid,)).fetchone()[0]


# --- платежи ---
def add_payment(charge_id, uid, item, stars) -> bool:
    """False, если платёж уже был записан (защита от двойного начисления)."""
    with conn() as c:
        try:
            c.execute("INSERT INTO payments VALUES(?,?,?,?,?,0)", (charge_id, uid, item, stars, time.time()))
            return True
        except sqlite3.IntegrityError:
            return False


def payments(limit=50):
    with conn() as c:
        return [dict(r) for r in c.execute(
            "SELECT p.*, u.name, u.username FROM payments p LEFT JOIN users u ON u.id=p.user_id "
            "ORDER BY p.created DESC LIMIT ?", (limit,))]


def get_payment(charge_id):
    with conn() as c:
        r = c.execute("SELECT * FROM payments WHERE charge_id=?", (charge_id,)).fetchone()
        return dict(r) if r else None


def mark_refunded(charge_id):
    with conn() as c:
        c.execute("UPDATE payments SET refunded=1 WHERE charge_id=?", (charge_id,))


# --- админка ---
def stats():
    day = time.time() - 86400
    with conn() as c:
        q = lambda sql, *a: c.execute(sql, a).fetchone()[0]
        return {
            "users": q("SELECT COUNT(*) FROM users"),
            "new_24h": q("SELECT COUNT(*) FROM users WHERE created>?", day),
            "active_24h": q("SELECT COUNT(*) FROM users WHERE last_claim>?", day),
            "stars_total": q("SELECT COALESCE(SUM(stars),0) FROM payments WHERE refunded=0"),
            "stars_24h": q("SELECT COALESCE(SUM(stars),0) FROM payments WHERE refunded=0 AND created>?", day),
            "payments": q("SELECT COUNT(*) FROM payments WHERE refunded=0"),
            "coins_total": q("SELECT COALESCE(SUM(balance),0) FROM users"),
        }


def search(q: str, limit=30):
    with conn() as c:
        if q.strip().lstrip("-").isdigit():
            rows = c.execute("SELECT * FROM users WHERE id=?", (int(q),))
        elif q.strip():
            like = f"%{q.strip().lstrip('@')}%"
            rows = c.execute("SELECT * FROM users WHERE name LIKE ? OR username LIKE ? "
                             "ORDER BY created DESC LIMIT ?", (like, like, limit))
        else:
            rows = c.execute("SELECT * FROM users ORDER BY created DESC LIMIT ?", (limit,))
        return [dict(r) for r in rows]


def all_ids():
    with conn() as c:
        return [r[0] for r in c.execute("SELECT id FROM users WHERE banned=0")]
