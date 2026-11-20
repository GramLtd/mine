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
        CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT);
        CREATE TABLE IF NOT EXISTS withdrawals(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            amount REAL,
            address TEXT,
            status TEXT DEFAULT 'pending',
            tx TEXT,
            created REAL,
            processed REAL
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
            "wd_pending": q("SELECT COUNT(*) FROM withdrawals WHERE status='pending'"),
            "wd_paid": q("SELECT COALESCE(SUM(amount),0) FROM withdrawals WHERE status='paid'"),
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


# --- настройки (меняются из админки) ---
def get_setting(key, default=None):
    with conn() as c:
        r = c.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return r[0] if r else default


def set_setting(key, value):
    with conn() as c:
        c.execute("INSERT INTO settings VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                  (key, str(value)))


# --- выводы ---
def create_withdrawal(uid, amount, address) -> int | None:
    """Атомарно списывает баланс и создаёт заявку. None — не хватает средств или уже есть заявка."""
    with conn() as c:
        if c.execute("SELECT 1 FROM withdrawals WHERE user_id=? AND status='pending'", (uid,)).fetchone():
            return None
        cur = c.execute("UPDATE users SET balance=balance-? WHERE id=? AND balance>=?", (amount, uid, amount))
        if cur.rowcount != 1:
            return None
        return c.execute("INSERT INTO withdrawals(user_id,amount,address,created) VALUES(?,?,?,?)",
                         (uid, amount, address, time.time())).lastrowid


def withdrawals(uid=None, status=None, limit=50):
    sql = ("SELECT w.*, u.name, u.username FROM withdrawals w LEFT JOIN users u ON u.id=w.user_id WHERE 1=1")
    args = []
    if uid is not None:
        sql += " AND w.user_id=?"; args.append(uid)
    if status:
        sql += " AND w.status=?"; args.append(status)
    sql += " ORDER BY w.id DESC LIMIT ?"; args.append(limit)
    with conn() as c:
        return [dict(r) for r in c.execute(sql, args)]


def finish_withdrawal(wid, status, tx=None):
    """status: paid | rejected. При отклонении монеты возвращаются. Возвращает заявку или None."""
    with conn() as c:
        w = c.execute("SELECT * FROM withdrawals WHERE id=? AND status='pending'", (wid,)).fetchone()
        if not w:
            return None
        c.execute("UPDATE withdrawals SET status=?, tx=?, processed=? WHERE id=?", (status, tx, time.time(), wid))
        if status == "rejected":
            c.execute("UPDATE users SET balance=balance+? WHERE id=?", (w["amount"], w["user_id"]))
        return dict(w)
