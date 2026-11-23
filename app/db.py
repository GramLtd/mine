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
        CREATE TABLE IF NOT EXISTS missions(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT, url TEXT, chat TEXT, reward REAL,
            active INTEGER DEFAULT 1, created REAL
        );
        CREATE TABLE IF NOT EXISTS mission_done(
            user_id INTEGER, mission_id INTEGER, created REAL,
            PRIMARY KEY(user_id, mission_id)
        );
        CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT);
        CREATE TABLE IF NOT EXISTS servers(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            tier INTEGER,
            created REAL,
            expires REAL,
            expiry_notified INTEGER DEFAULT 0
        );
        CREATE INDEX IF NOT EXISTS servers_user ON servers(user_id);
        CREATE TABLE IF NOT EXISTS stock(tier INTEGER PRIMARY KEY, left INTEGER, period INTEGER);
        CREATE TABLE IF NOT EXISTS checks(
            nonce TEXT PRIMARY KEY,
            creator INTEGER,
            amount REAL,
            status TEXT,          -- active (сумма зарезервирована), claimed, cancelled, failed
            claimer INTEGER,
            created REAL,
            finished REAL
        );
        CREATE TABLE IF NOT EXISTS mchecks(
            nonce TEXT PRIMARY KEY,
            creator INTEGER,
            amount REAL,          -- сумма одной активации
            total INTEGER,        -- сколько активаций
            claimed INTEGER DEFAULT 0,
            status TEXT,          -- active, done, cancelled, failed
            created REAL
        );
        CREATE TABLE IF NOT EXISTS mcheck_claims(nonce TEXT, user_id INTEGER, created REAL, PRIMARY KEY(nonce, user_id));
        CREATE TABLE IF NOT EXISTS ton_orders(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            item TEXT,
            nano INTEGER,
            comment TEXT UNIQUE,
            status TEXT DEFAULT 'pending',
            tx TEXT UNIQUE,
            created REAL,
            paid REAL
        );
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
                         ("boost_until", "REAL DEFAULT 0"), ("banned", "INTEGER DEFAULT 0"),
                         ("storage_hours", "REAL DEFAULT 0"), ("skins", "TEXT DEFAULT ''"),
                         ("skin", "TEXT DEFAULT ''"), ("full_notified", "REAL DEFAULT 0")]:
            if col not in cols:
                c.execute(f"ALTER TABLE users ADD COLUMN {col} {ddl}")
        if "activated" not in cols:
            c.execute("ALTER TABLE users ADD COLUMN activated INTEGER DEFAULT 1")
        for col, ddl in [("no_fee", "INTEGER DEFAULT 0"), ("bought_server", "INTEGER DEFAULT 0"), ("tutorial_done", "INTEGER DEFAULT 0"), ("acc", "REAL DEFAULT 0"), ("acc_since", "REAL DEFAULT 0"), ("lang", "TEXT DEFAULT ''")]:
            if col not in cols:
                c.execute(f"ALTER TABLE users ADD COLUMN {col} {ddl}")
        wcols = {r["name"] for r in c.execute("PRAGMA table_info(withdrawals)")}
        if "reason" not in wcols:
            c.execute("ALTER TABLE withdrawals ADD COLUMN reason TEXT")
        if "ref_paid" not in cols:  # бонус за друга — когда он арендует первый сервер; старым не платим повторно
            c.execute("ALTER TABLE users ADD COLUMN ref_paid INTEGER DEFAULT 0")
            c.execute("UPDATE users SET ref_paid=1 WHERE bought_server=1")
        # переход с уровней на серверы: игрокам с запущенным майнингом — сервер их уровня на 30 дней
        if not c.execute("SELECT value FROM settings WHERE key='servers_migrated'").fetchone():
            now = time.time()
            c.execute("INSERT INTO servers(user_id,tier,created,expires) "
                      "SELECT id, level, ?, ? FROM users WHERE activated=1", (now, now + 30 * 86400))
            c.execute("UPDATE users SET bought_server=1 WHERE activated=1")
            c.execute("INSERT INTO settings VALUES('servers_migrated','1')")


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


def spend(uid: int, amount: float) -> bool:
    """Атомарно списать с баланса, если хватает."""
    with conn() as c:
        return c.execute("UPDATE users SET balance=balance-? WHERE id=? AND balance>=?",
                         (amount, uid, amount)).rowcount == 1


def add_balance(uid: int, amount: float):
    with conn() as c:
        c.execute("UPDATE users SET balance=balance+? WHERE id=?", (amount, uid))


def friends(uid: int):
    with conn() as c:
        return [dict(r) for r in c.execute(
            "SELECT id,name,(SELECT COUNT(*) FROM servers s WHERE s.user_id=users.id AND s.expires>strftime('%s','now')) AS servers FROM users WHERE referrer=? ORDER BY created DESC", (uid,))]


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


def finish_withdrawal(wid, status, tx=None, reason=None):
    """status: paid | rejected. При отклонении монеты возвращаются. Возвращает заявку или None."""
    with conn() as c:
        w = c.execute("SELECT * FROM withdrawals WHERE id=? AND status='pending'", (wid,)).fetchone()
        if not w:
            return None
        c.execute("UPDATE withdrawals SET status=?, tx=?, reason=?, processed=? WHERE id=?",
                  (status, tx, reason, time.time(), wid))
        if status == "rejected":
            c.execute("UPDATE users SET balance=balance+? WHERE id=?", (w["amount"], w["user_id"]))
        return dict(w)


# --- задания от рекламодателей ---
def missions_list(active_only=True):
    with conn() as c:
        sql = "SELECT * FROM missions" + (" WHERE active=1" if active_only else "") + " ORDER BY id DESC"
        return [dict(r) for r in c.execute(sql)]


def mission_get(mid):
    with conn() as c:
        r = c.execute("SELECT * FROM missions WHERE id=?", (mid,)).fetchone()
        return dict(r) if r else None


def mission_add(title, url, chat, reward):
    with conn() as c:
        return c.execute("INSERT INTO missions(title,url,chat,reward,created) VALUES(?,?,?,?,?)",
                         (title, url, chat, reward, time.time())).lastrowid


def mission_set_active(mid, active):
    with conn() as c:
        c.execute("UPDATE missions SET active=? WHERE id=?", (int(active), mid))


def mission_done_ids(uid):
    with conn() as c:
        return {r[0] for r in c.execute("SELECT mission_id FROM mission_done WHERE user_id=?", (uid,))}


def mission_complete(uid, mid) -> bool:
    with conn() as c:
        try:
            c.execute("INSERT INTO mission_done VALUES(?,?,?)", (uid, mid, time.time()))
            return True
        except sqlite3.IntegrityError:
            return False


def mission_counts():
    with conn() as c:
        return {r[0]: r[1] for r in c.execute("SELECT mission_id, COUNT(*) FROM mission_done GROUP BY mission_id")}


# ---------- оплата в TON ----------
def ton_order_create(uid, item, nano, comment) -> int:
    with conn() as c:
        return c.execute("INSERT INTO ton_orders(user_id,item,nano,comment,created) VALUES(?,?,?,?,?)",
                         (uid, item, nano, comment, time.time())).lastrowid


def ton_order_get(oid):
    with conn() as c:
        r = c.execute("SELECT * FROM ton_orders WHERE id=?", (oid,)).fetchone()
        return dict(r) if r else None


def ton_orders_pending(since):
    with conn() as c:
        return [dict(r) for r in c.execute(
            "SELECT * FROM ton_orders WHERE status='pending' AND created>?", (since,))]


def ton_order_mark_paid(oid, tx) -> bool:
    """Атомарно: True только у первого, кто отметил заказ (защита от двойного начисления)."""
    with conn() as c:
        try:
            cur = c.execute("UPDATE ton_orders SET status='paid', tx=?, paid=? WHERE id=? AND status='pending'",
                            (tx, time.time(), oid))
        except sqlite3.IntegrityError:
            return False
        return cur.rowcount == 1


def ton_orders(limit=50):
    with conn() as c:
        return [dict(r) for r in c.execute(
            "SELECT * FROM ton_orders WHERE status='paid' ORDER BY paid DESC LIMIT ?", (limit,))]


def storage_full_users(now, base_hours, limit=200):
    """Игроки, у которых хранилище заполнилось и по этому заходу ещё не было уведомления."""
    with conn() as c:
        return [dict(r) for r in c.execute(
            "SELECT * FROM users u WHERE banned=0 AND full_notified < last_claim "
            "AND last_claim + MAX(?, COALESCE(storage_hours,0)) * 3600 <= ? "
            "AND EXISTS(SELECT 1 FROM servers s WHERE s.user_id=u.id AND s.expires > u.last_claim) LIMIT ?",
            (base_hours, now, limit))]


# ---------- серверы ----------
def servers(uid, include_expired_days=7):
    with conn() as c:
        return [dict(r) for r in c.execute(
            "SELECT * FROM servers WHERE user_id=? AND expires>? ORDER BY tier DESC, id",
            (uid, time.time() - include_expired_days * 86400))]


def server_get(sid):
    with conn() as c:
        r = c.execute("SELECT * FROM servers WHERE id=?", (sid,)).fetchone()
        return dict(r) if r else None


def server_add(uid, tier, days):
    now = time.time()
    with conn() as c:
        return c.execute("INSERT INTO servers(user_id,tier,created,expires) VALUES(?,?,?,?)",
                         (uid, tier, now, now + days * 86400)).lastrowid


def server_update(sid, **f):
    with conn() as c:
        c.execute(f"UPDATE servers SET {', '.join(k + '=?' for k in f)} WHERE id=?", (*f.values(), sid))


def servers_expired_unnotified(now):
    with conn() as c:
        return [dict(r) for r in c.execute(
            "SELECT s.* FROM servers s JOIN users u ON u.id=s.user_id "
            "WHERE s.expires<=? AND s.expiry_notified=0 AND u.banned=0 LIMIT 200", (now,))]


# ---------- склад ----------
def stock_get(tier, period, daily):
    with conn() as c:
        r = c.execute("SELECT left, period FROM stock WHERE tier=?", (tier,)).fetchone()
        if not r or r["period"] != period:
            c.execute("INSERT INTO stock VALUES(?,?,?) ON CONFLICT(tier) DO UPDATE SET left=excluded.left, period=excluded.period",
                      (tier, daily, period))
            return daily
        return r["left"]


def stock_take(tier, period, daily) -> bool:
    stock_get(tier, period, daily)
    with conn() as c:
        return c.execute("UPDATE stock SET left=left-1 WHERE tier=? AND period=? AND left>0",
                         (tier, period)).rowcount == 1


def stock_set(tier, period, left):
    with conn() as c:
        c.execute("INSERT INTO stock VALUES(?,?,?) ON CONFLICT(tier) DO UPDATE SET left=excluded.left, period=excluded.period",
                  (tier, max(0, left), period))


def ref_unpaid(limit=200):
    """Приглашённые, которые арендовали первый сервер, а бонус пригласившему ещё не выплачен."""
    with conn() as c:
        return [dict(r) for r in c.execute(
            "SELECT id, name, referrer FROM users WHERE referrer IS NOT NULL AND bought_server=1 AND ref_paid=0 LIMIT ?",
            (limit,))]


def ref_mark_paid(uid) -> bool:
    with conn() as c:
        return c.execute("UPDATE users SET ref_paid=1 WHERE id=? AND ref_paid=0", (uid,)).rowcount == 1


# ---------- чеки ----------
def check_get(nonce):
    with conn() as c:
        r = c.execute("SELECT * FROM checks WHERE nonce=?", (nonce,)).fetchone()
        return dict(r) if r else None


def check_reserve(nonce, creator, amount) -> str:
    """Чек отправлен в чат: списываем сумму с баланса создателя (резерв). Всё в одной транзакции."""
    with conn() as c:
        c.execute("BEGIN IMMEDIATE")
        if c.execute("SELECT 1 FROM checks WHERE nonce=?", (nonce,)).fetchone():
            return "exists"  # уже получен/обработан
        ok = c.execute("UPDATE users SET balance=balance-? WHERE id=? AND balance>=?",
                       (amount, creator, amount)).rowcount == 1
        c.execute("INSERT INTO checks(nonce,creator,amount,status,created) VALUES(?,?,?,?,?)",
                  (nonce, creator, amount, "active" if ok else "failed", time.time()))
        return "active" if ok else "failed"


def check_claim(nonce, creator, amount, claimer) -> str:
    """Получить чек. Если резерва не было (не пришёл chosen_inline_result) — списываем с создателя сейчас."""
    with conn() as c:
        c.execute("BEGIN IMMEDIATE")
        r = c.execute("SELECT status FROM checks WHERE nonce=?", (nonce,)).fetchone()
        if r and r["status"] != "active":
            return r["status"]
        if not r:
            if c.execute("UPDATE users SET balance=balance-? WHERE id=? AND balance>=?",
                         (amount, creator, amount)).rowcount != 1:
                return "no_funds"
            c.execute("INSERT INTO checks(nonce,creator,amount,status,created) VALUES(?,?,?,?,?)",
                      (nonce, creator, amount, "active", time.time()))
        c.execute("UPDATE checks SET status='claimed', claimer=?, finished=? WHERE nonce=?", (claimer, time.time(), nonce))
        c.execute("UPDATE users SET balance=balance+? WHERE id=?", (amount, claimer))
        return "ok"


def check_cancel(nonce, creator, amount) -> str:
    """Создатель нажал на свой чек — отмена и возврат суммы, если она была зарезервирована."""
    with conn() as c:
        c.execute("BEGIN IMMEDIATE")
        r = c.execute("SELECT status FROM checks WHERE nonce=?", (nonce,)).fetchone()
        if r and r["status"] != "active":
            return r["status"]
        if r:
            c.execute("UPDATE users SET balance=balance+? WHERE id=?", (amount, creator))
            c.execute("UPDATE checks SET status='cancelled', finished=? WHERE nonce=?", (time.time(), nonce))
        else:
            c.execute("INSERT INTO checks(nonce,creator,amount,status,created,finished) VALUES(?,?,?,'cancelled',?,?)",
                      (nonce, creator, amount, time.time(), time.time()))
        return "ok"


# ---------- мультичеки: одна ссылка, N активаций по amount ----------
def mcheck_get(nonce):
    with conn() as c:
        r = c.execute("SELECT * FROM mchecks WHERE nonce=?", (nonce,)).fetchone()
        return dict(r) if r else None


def mcheck_reserve(nonce, creator, amount, total) -> str:
    with conn() as c:
        c.execute("BEGIN IMMEDIATE")
        if c.execute("SELECT 1 FROM mchecks WHERE nonce=?", (nonce,)).fetchone():
            return "exists"
        s = amount * total
        ok = c.execute("UPDATE users SET balance=balance-? WHERE id=? AND balance>=?", (s, creator, s)).rowcount == 1
        c.execute("INSERT INTO mchecks(nonce,creator,amount,total,status,created) VALUES(?,?,?,?,?,?)",
                  (nonce, creator, amount, total, "active" if ok else "failed", time.time()))
        return "active" if ok else "failed"


def mcheck_claim(nonce, creator, amount, total, claimer):
    """Возвращает (статус, сколько активаций уже использовано)."""
    with conn() as c:
        c.execute("BEGIN IMMEDIATE")
        r = c.execute("SELECT * FROM mchecks WHERE nonce=?", (nonce,)).fetchone()
        if not r:  # резерва не было — списываем всю сумму мультичека при первой активации
            s = amount * total
            if c.execute("UPDATE users SET balance=balance-? WHERE id=? AND balance>=?", (s, creator, s)).rowcount != 1:
                return "no_funds", 0
            c.execute("INSERT INTO mchecks(nonce,creator,amount,total,status,created) VALUES(?,?,?,?,?,?)",
                      (nonce, creator, amount, total, "active", time.time()))
            r = c.execute("SELECT * FROM mchecks WHERE nonce=?", (nonce,)).fetchone()
        if r["status"] != "active":
            return r["status"], r["claimed"]
        if c.execute("SELECT 1 FROM mcheck_claims WHERE nonce=? AND user_id=?", (nonce, claimer)).fetchone():
            return "already", r["claimed"]
        c.execute("INSERT INTO mcheck_claims VALUES(?,?,?)", (nonce, claimer, time.time()))
        n = r["claimed"] + 1
        c.execute("UPDATE mchecks SET claimed=?, status=? WHERE nonce=?", (n, "done" if n >= r["total"] else "active", nonce))
        c.execute("UPDATE users SET balance=balance+? WHERE id=?", (r["amount"], claimer))
        return "ok", n


def mcheck_cancel(nonce, creator, amount, total):
    """Отмена создателем: остаток (неактивированные доли) возвращается. Возвращает (статус, сумма возврата)."""
    with conn() as c:
        c.execute("BEGIN IMMEDIATE")
        r = c.execute("SELECT * FROM mchecks WHERE nonce=?", (nonce,)).fetchone()
        if r and r["status"] != "active":
            return r["status"], 0
        if not r:
            c.execute("INSERT INTO mchecks(nonce,creator,amount,total,status,created) VALUES(?,?,?,?,'cancelled',?)",
                      (nonce, creator, amount, total, time.time()))
            return "ok", 0
        back = r["amount"] * (r["total"] - r["claimed"])
        c.execute("UPDATE users SET balance=balance+? WHERE id=?", (back, creator))
        c.execute("UPDATE mchecks SET status='cancelled' WHERE nonce=?", (nonce,))
        return "ok", back
