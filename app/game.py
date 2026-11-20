import time
from . import db
from .config import (LEVELS, COIN_PER_GH_PER_SEC, STORAGE_HOURS, REF_HASH_BONUS,
                     REF_HASH_BONUS_MAX, COIN)


def hashrate(user) -> float:
    base = LEVELS[user["level"]][0]
    n = len(db.friends(user["id"]))
    return base * (1 + min(n * REF_HASH_BONUS, REF_HASH_BONUS_MAX))


def pending(user, now=None) -> float:
    now = now or time.time()
    secs = min(now - user["last_claim"], STORAGE_HOURS * 3600)
    return max(secs, 0) * hashrate(user) * COIN_PER_GH_PER_SEC


def state(user) -> dict:
    lvl = user["level"]
    nxt = LEVELS[lvl + 1] if lvl + 1 < len(LEVELS) else None
    return {
        "coin": COIN,
        "balance": user["balance"],
        "pending": pending(user),
        "hashrate": hashrate(user),
        "rate_per_sec": hashrate(user) * COIN_PER_GH_PER_SEC,
        "storage_hours": STORAGE_HOURS,
        "server_time": time.time(),
        "last_claim": user["last_claim"],
        "level": lvl + 1,
        "next_level": {"hashrate": nxt[0], "price": nxt[1]} if nxt else None,
    }
