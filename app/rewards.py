"""Программа вознаграждений: еженедельный призовой фонд из доли выручки, делится по игровой активности.

Выплаты не зависят от того, сколько игрок заплатил, и не могут превысить фонд (REWARD_SHARE выручки)
и лимит на игрока (REWARD_CAP). Очки = TON CRY, собранные кнопкой «Claim» за неделю (только у игроков
с хотя бы одним оплаченным сервером).
"""
import time
from datetime import datetime, timedelta, timezone

from . import db, settings
from .config import REWARD_SHARE, REWARD_CAP

MSK = timezone(timedelta(hours=3))


def share() -> float:
    return min(0.5, max(0.0, float(db.get_setting("reward_share", REWARD_SHARE))))


def cap() -> float:
    return max(0.0, float(db.get_setting("reward_cap", REWARD_CAP)))


def week_start(ts=None) -> float:
    dt = datetime.fromtimestamp(ts or time.time(), MSK)
    monday = (dt - timedelta(days=dt.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    return monday.timestamp()


def week_id(ts=None) -> int:
    return datetime.fromtimestamp(week_start(ts), MSK).toordinal()


def stars_to_ton() -> float:
    return settings.star_rub() / settings.ton_rub()


def add_points(user, amount):
    if amount > 0 and user.get("bought_server"):
        db.points_add(week_id(), user["id"], amount)


def current(user) -> dict:
    start = week_start()
    rev = db.revenue_between(start, time.time(), stars_to_ton())
    fund = rev * share()
    mine, total = db.week_points(week_id(), user["id"])
    est = min(cap(), fund * mine / total) if total > 0 and user.get("bought_server") else 0.0
    return {"fund": round(fund, 4), "points": mine, "total_points": total, "estimate": round(est, 4),
            "ends_at": start + 7 * 86400, "share": share(), "cap": cap(), "eligible": bool(user.get("bought_server")),
            "balance": user.get("reward_balance") or 0.0, "history": db.reward_history(user["id"], 5)}


def distribute_due():
    """Вызывается из фонового цикла: распределяет прошлую неделю, если ещё не распределена."""
    prev_start = week_start() - 7 * 86400
    wk = week_id(prev_start)
    if db.reward_week_done(wk):
        return []
    rev = db.revenue_between(prev_start, prev_start + 7 * 86400, stars_to_ton())
    return db.distribute_week(wk, rev, rev * share(), cap())
