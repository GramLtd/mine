import math
import time
from datetime import datetime, timedelta, timezone

from . import db, settings, i18n
from .config import (SERVERS, RENT_DAYS, FIRST_DISCOUNT, UPGRADE_MARKUP, MINING_FEE, NOFEE_PRICE,
                     STOCK_RESET_HOUR_MSK, COIN_PER_GH_PER_SEC, STORAGE_HOURS, SHOP, STORAGE_ITEMS)

MSK = timezone(timedelta(hours=3))


# ---------- тарифы ----------
def tier_hashrate(t) -> int:
    """GH/s, при котором сервер окупает аренду за свои «дни окупаемости» (без комиссии и бонусов)."""
    _c, _r, price, payback, _s = SERVERS[t]
    return round(price / payback / 86400 / COIN_PER_GH_PER_SEC)


def tier_price(t) -> float:
    return float(SERVERS[t][2])


def daily_stock(t) -> int:
    return int(db.get_setting(f"stock_daily_{t}", SERVERS[t][4]))


def stock_period(now=None) -> int:
    """Номер «складских суток»: меняется каждый день в 12:00 МСК."""
    dt = datetime.fromtimestamp(now or time.time(), MSK) - timedelta(hours=STOCK_RESET_HOUR_MSK)
    return dt.toordinal()


def next_restock(now=None) -> float:
    dt = datetime.fromtimestamp(now or time.time(), MSK)
    r = dt.replace(hour=STOCK_RESET_HOUR_MSK, minute=0, second=0, microsecond=0)
    if r <= dt:
        r += timedelta(days=1)
    return r.timestamp()


def stock_left(t) -> int:
    return db.stock_get(t, stock_period(), daily_stock(t))


def tier_info(t, discount=False):
    c, r, price, payback, _s = SERVERS[t]
    word = "ядро" if c % 10 == 1 and c % 100 != 11 else "ядра" if 2 <= c % 10 <= 4 and not 12 <= c % 100 <= 14 else "ядер"
    final = round(price * (1 - FIRST_DISCOUNT), 2) if discount else price
    return {"tier": t, "cores": c, "ram": r, "spec": f"{c} {word} / {r} GB RAM", "hashrate": tier_hashrate(t),
            "price": final, "full_price": price, "payback": payback, "daily_income": round(price / payback, 3), "stock": stock_left(t), "daily": daily_stock(t)}


def upgrade_price(t) -> float:
    return round((tier_price(t + 1) - tier_price(t)) * UPGRADE_MARKUP, 2)


# ---------- доход ----------
def ref_mult(user) -> float:
    return 1.0  # бонус к хешрейту за друзей убран; за друга платится ref_bonus


def fee(user) -> float:
    return 0.0 if user.get("no_fee") else MINING_FEE


def boost(user, now=None) -> float:
    now = now or time.time()
    return user.get("boost_mult") or 1 if (user.get("boost_until") or 0) > now else 1


def storage_hours(user) -> float:
    return max(STORAGE_HOURS, user.get("storage_hours") or 0)


def active_servers(user, now=None):
    now = now or time.time()
    return [s for s in db.servers(user["id"], 0) if s["expires"] > now]


def hashrate(user, now=None) -> float:
    """Текущий суммарный хешрейт (с рефералами и бустом)."""
    now = now or time.time()
    return sum(tier_hashrate(s["tier"]) for s in active_servers(user, now)) * ref_mult(user) * boost(user, now)


def storage_end(user) -> float:
    """Хранилище заполняется за storage_hours после последнего «Забрать» — дальше майнинг стоит."""
    return user["last_claim"] + storage_hours(user) * 3600


def pending(user, now=None) -> float:
    """Накоплено в хранилище: зафиксированная часть (acc) + начисление с момента фиксации по текущим серверам."""
    now = now or time.time()
    acc = user.get("acc") or 0.0
    start = max(user["last_claim"], user.get("acc_since") or 0)
    now = min(now, storage_end(user))
    if now <= start:
        return acc
    bu, mult = user.get("boost_until") or 0, user.get("boost_mult") or 1
    gh_secs = 0.0
    for s in db.servers(user["id"], 0):
        end = min(now, s["expires"])
        a = max(start, s["created"])
        if end <= a:
            continue
        boosted = max(0.0, min(end, bu) - a)
        gh_secs += tier_hashrate(s["tier"]) * ((end - a - boosted) + boosted * mult)
    return acc + gh_secs * ref_mult(user) * COIN_PER_GH_PER_SEC * (1 - fee(user))


def rebase(user, now=None):
    """Зафиксировать накопленное по старой мощности, не забирая его, — дальше майнинг идёт с новой мощностью."""
    now = now or time.time()
    amount = pending(user, now)
    if amount <= 0:  # ничего не накоплено (например, первый сервер) — новый цикл хранилища с этого момента
        db.update(user["id"], acc=0.0, acc_since=now, last_claim=now)
    else:
        db.update(user["id"], acc=amount, acc_since=now)


def settle(user, now=None):
    """«Забрать»: перевести накопленное на баланс и начать новый цикл хранилища."""
    now = now or time.time()
    amount = pending(user, now)
    db.update(user["id"], balance=user["balance"] + amount, last_claim=now, acc=0.0, acc_since=now)
    return amount


# ---------- товары: srv:<tier>, upg:<server_id>, ren:<server_id>, nofee, topup, товары SHOP ----------
class NotBuyable(Exception):
    pass


def item_title(item) -> str:
    kind, _, arg = item.partition(":")
    if kind == "srv":
        return f"Сервер {tier_info(int(arg))['spec']}"
    if kind in ("upg", "ren"):
        s = db.server_get(int(arg))
        spec = tier_info(s["tier"])["spec"] if s else "сервер"
        return f"Улучшение: {spec}" if kind == "upg" else f"Продление: {spec}"
    if item == "nofee":
        return "Отключение комиссии"
    if item == "topup":
        return "Пополнение баланса"
    return SHOP[item][0] if item in SHOP else "Покупка"


def check(user, item):
    """Проверить, что товар можно купить; бросает NotBuyable с причиной."""
    kind, _, arg = item.partition(":")
    if kind == "srv":
        if not arg.isdigit() or not 0 <= int(arg) < len(SERVERS):
            raise NotBuyable("Нет такого сервера")
        if stock_left(int(arg)) <= 0:
            raise NotBuyable("Этот сервер закончился, пополнение в 12:00 МСК")
    elif kind in ("upg", "ren"):
        s = db.server_get(int(arg)) if arg.isdigit() else None
        if not s or s["user_id"] != user["id"]:
            raise NotBuyable("Сервер не найден")
        if kind == "upg":
            if s["expires"] <= time.time():
                raise NotBuyable("Аренда истекла — сначала продлите сервер")
            if s["tier"] + 1 >= len(SERVERS):
                raise NotBuyable("Это максимальный тариф")
    elif item == "nofee":
        if user.get("no_fee"):
            raise NotBuyable("Комиссия уже отключена")
    elif item in SHOP:
        if item.startswith("skin_") and item in (user.get("skins") or "").split(","):
            raise NotBuyable("Скин уже куплен")
        if item in STORAGE_ITEMS and storage_hours(user) >= STORAGE_ITEMS[item]:
            raise NotBuyable("Уже есть такое или большее хранилище")
    elif item != "topup":
        raise NotBuyable("Нет такого товара")


def price_ton(user, item) -> float:
    kind, _, arg = item.partition(":")
    if kind == "srv":
        return tier_info(int(arg), discount=not user.get("bought_server"))["price"]
    if kind == "upg":
        return upgrade_price(db.server_get(int(arg))["tier"])
    if kind == "ren":
        return tier_price(db.server_get(int(arg))["tier"])
    if item == "nofee":
        return float(db.get_setting("nofee_price", NOFEE_PRICE))
    return settings.stars_to_ton(SHOP[item][2])


def price_stars(user, item) -> int:
    if item in SHOP:
        return SHOP[item][2]
    return settings.ton_to_stars(price_ton(user, item))


def apply_item(uid: int, item: str, paid_ton: float = 0.0) -> str | None:
    """Выдать товар. Если выдать уже нельзя (сервер закончился и т.п.) — вернуть paid_ton на баланс.
    Возвращает текст причины возврата или None."""
    user = db.get(uid)
    now = time.time()
    kind, _, arg = item.partition(":")
    try:
        check(user, item) if kind != "srv" else None
    except NotBuyable as e:
        if paid_ton:
            db.add_balance(uid, paid_ton)
        return str(e)
    if kind == "srv":
        t = int(arg)
        if not db.stock_take(t, stock_period(now), daily_stock(t)):
            if paid_ton:
                db.add_balance(uid, paid_ton)
            return "Сервер закончился на складе — оплата возвращена на баланс"
        rebase(user, now)
        db.server_add(uid, t, RENT_DAYS)
        db.update(uid, bought_server=1)
    elif kind == "upg":
        s = db.server_get(int(arg))
        rebase(user, now)
        db.server_update(s["id"], tier=s["tier"] + 1)
    elif kind == "ren":
        s = db.server_get(int(arg))
        rebase(user, now)
        if s["expires"] <= now:  # истёкший сервер запускается заново
            db.server_update(s["id"], created=now, expires=now + RENT_DAYS * 86400, expiry_notified=0)
        else:
            db.server_update(s["id"], expires=s["expires"] + RENT_DAYS * 86400, expiry_notified=0)
    elif item == "nofee":
        rebase(user, now)
        db.update(uid, no_fee=1)
    elif item in ("boost2", "boost3"):
        mult = 2 if item == "boost2" else 3
        rebase(user, now)
        cur_until = user["boost_until"] if user["boost_until"] > now and user["boost_mult"] == mult else now
        db.update(uid, boost_mult=mult, boost_until=cur_until + 86400)
    elif item in STORAGE_ITEMS:
        rebase(user, now)
        db.update(uid, storage_hours=max(storage_hours(user), STORAGE_ITEMS[item]))
    elif item.startswith("skin_"):
        owned = set(filter(None, (user.get("skins") or "").split(",")))
        owned.add(item)
        db.update(uid, skins=",".join(sorted(owned)), skin=item)
    elif paid_ton:  # неизвестный/устаревший товар — деньги на баланс
        db.add_balance(uid, paid_ton)
        return "Товар недоступен — оплата возвращена на баланс"
    return None


def state(user, is_admin=False) -> dict:
    now = time.time()
    b = boost(user, now)
    hr = hashrate(user, now)
    first = not user.get("bought_server")
    my = []
    for s in db.servers(user["id"]):
        info = tier_info(s["tier"])
        my.append({"id": s["id"], "spec": info["spec"], "hashrate": info["hashrate"], "tier": s["tier"],
                   "daily_income": info["daily_income"],
                   "expires": s["expires"], "active": s["expires"] > now,
                   "upgrade": ({"price": upgrade_price(s["tier"]), **{k: v for k, v in tier_info(s["tier"] + 1).items()
                                                                      if k in ("spec", "hashrate")}}
                               if s["tier"] + 1 < len(SERVERS) else None),
                   "renew": tier_price(s["tier"])})
    ton_on = settings.ton_enabled()
    f = fee(user)
    return {
        "coin": settings.coin(),
        "min_withdraw": settings.min_withdraw(),
        "withdraw_enabled": settings.withdraw_enabled(),
        "balance": user["balance"],
        "pending": pending(user, now),
        "storage_end": storage_end(user),
        "server_time": now,
        "hashrate": hr,
        "rate_per_sec": hr * COIN_PER_GH_PER_SEC * (1 - f),
        "storage_hours": storage_hours(user),
        "skins": [x for x in (user.get("skins") or "").split(",") if x],
        "skin": user.get("skin") or "",
        "boost": {"mult": b, "until": user["boost_until"]} if b > 1 else None,
        "servers": [tier_info(t, discount=first) for t in range(len(SERVERS))],
        "my_servers": my,
        "active_count": sum(1 for s in my if s["active"]),
        "first_discount": FIRST_DISCOUNT if first else 0,
        "rent_days": RENT_DAYS,
        "restock_at": next_restock(now),
        "fee": f,
        "nofee_price": float(db.get_setting("nofee_price", NOFEE_PRICE)),
        "ton_enabled": ton_on,
        "star_rate": settings.ton_rub() / settings.star_rub(),
        "shop": [{"id": k, "title": i18n.t(t), "desc": i18n.t(d), "stars": p, "cat": c, "ton": settings.stars_to_ton(p)}
                 for k, (t, d, p, c) in SHOP.items()],
        "is_admin": is_admin,
        "tutorial_done": bool(user.get("tutorial_done")),
    }
