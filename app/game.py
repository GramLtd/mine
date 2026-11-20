import time
from . import db
from .config import (LEVELS, COIN_PER_GH_PER_SEC, STORAGE_HOURS, REF_HASH_BONUS,
                     REF_HASH_BONUS_MAX, SHOP, STORAGE_ITEMS)
from . import settings


def base_hashrate(user) -> float:
    n = db.friend_count(user["id"])
    return LEVELS[user["level"]][0] * (1 + min(n * REF_HASH_BONUS, REF_HASH_BONUS_MAX))


def boost(user, now=None) -> float:
    now = now or time.time()
    return user.get("boost_mult") or 1 if (user.get("boost_until") or 0) > now else 1


def storage_hours(user) -> float:
    return max(STORAGE_HOURS, user.get("storage_hours") or 0)


def pending(user, now=None) -> float:
    """Начисление за период [last_claim, now] с учётом буста, который мог закончиться посередине."""
    now = now or time.time()
    start = max(user["last_claim"], now - storage_hours(user) * 3600)
    if now <= start:
        return 0.0
    secs = now - start
    boosted = max(0.0, min(now, user.get("boost_until") or 0) - start)
    mult = user.get("boost_mult") or 1
    eff = (secs - boosted) + boosted * mult
    return eff * base_hashrate(user) * COIN_PER_GH_PER_SEC


def settle(user, now=None):
    """Зачислить накопленное в «хранилище» и сбросить таймер (перед изменением скорости)."""
    now = now or time.time()
    acc = pending(user, now)
    db.update(user["id"], balance=user["balance"] + acc, last_claim=now)
    return acc


def apply_item(uid: int, item: str):
    user = db.get(uid)
    now = time.time()
    if item in ("boost2", "boost3"):
        mult = 2 if item == "boost2" else 3
        # копим монеты, но не забираем из хранилища: переносим по старой скорости
        acc = pending(user, now)
        cur_until = user["boost_until"] if user["boost_until"] > now and user["boost_mult"] == mult else now
        db.update(uid, balance=user["balance"] + acc, last_claim=now,
                  boost_mult=mult, boost_until=cur_until + 86400)
    elif item in STORAGE_ITEMS:
        settle(user, now)
        db.update(uid, storage_hours=max(storage_hours(user), STORAGE_ITEMS[item]))
    elif item.startswith("skin_"):
        owned = set(filter(None, (user.get("skins") or "").split(",")))
        owned.add(item)
        db.update(uid, skins=",".join(sorted(owned)), skin=item)
    elif item == "level":
        if user["level"] + 1 < len(LEVELS):
            settle(user, now)
            db.update(uid, level=user["level"] + 1)
        else:
            db.update(uid, boost_mult=2, boost_until=max(now, user["boost_until"]) + 2 * 86400)  # компенсация


def state(user, is_admin=False) -> dict:
    lvl = user["level"]
    nxt = LEVELS[lvl + 1] if lvl + 1 < len(LEVELS) else None
    now = time.time()
    b = boost(user, now)
    hr = base_hashrate(user) * b
    return {
        "coin": settings.coin(),
        "min_withdraw": settings.min_withdraw(),
        "withdraw_enabled": settings.withdraw_enabled(),
        "balance": user["balance"],
        "pending": pending(user, now),
        "hashrate": hr,
        "rate_per_sec": hr * COIN_PER_GH_PER_SEC,
        "storage_hours": storage_hours(user),
        "skins": [x for x in (user.get("skins") or "").split(",") if x],
        "skin": user.get("skin") or "",
        "level": lvl + 1,
        "max_level": len(LEVELS),
        "boost": {"mult": b, "until": user["boost_until"]} if b > 1 else None,
        "next_level": {"hashrate": nxt[0], "price": nxt[1]} if nxt else None,
        "shop": [{"id": k, "title": t, "desc": d, "stars": p, "cat": c} for k, (t, d, p, c) in SHOP.items()],
        "is_admin": is_admin,
    }
