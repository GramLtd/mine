import sqlite3
from config import DB_PATH

conn = sqlite3.connect(DB_PATH, check_same_thread=False)
conn.row_factory = sqlite3.Row


def init():
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS wallets(
        address TEXT PRIMARY KEY,
        label TEXT,
        last_lt INTEGER DEFAULT 0
    );
    CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT);
    """)
    conn.commit()


def get(key, default=None):
    r = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return r["value"] if r else default


def set(key, value):
    conn.execute("INSERT OR REPLACE INTO settings VALUES(?,?)", (key, str(value)))
    conn.commit()


def add_wallet(address, label, last_lt):
    conn.execute("INSERT OR REPLACE INTO wallets VALUES(?,?,?)", (address, label, last_lt))
    conn.commit()


def remove_wallet(address):
    cur = conn.execute("DELETE FROM wallets WHERE address=?", (address,))
    conn.commit()
    return cur.rowcount > 0


def wallets():
    return conn.execute("SELECT * FROM wallets").fetchall()


def set_lt(address, lt):
    conn.execute("UPDATE wallets SET last_lt=? WHERE address=?", (lt, address))
    conn.commit()
