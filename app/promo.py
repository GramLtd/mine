"""Автосообщения игрокам (напоминания), чтобы возвращать в игру и предлагать следующий шаг.

Честно и без спама: каждый сценарий — максимум один раз на игрока, не больше одного автосообщения в сутки,
только 10:00–22:00 МСК, под каждым сообщением кнопка «Stop reminders». Тексты — без обещаний дохода.
"""
import asyncio
import json
import logging
import time
from datetime import datetime, timedelta, timezone

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo

from . import db
from .config import WEBAPP_URL

log = logging.getLogger("toncry.promo")
MSK = timezone(timedelta(hours=3))

# key: (название в админке, задержка в часах по умолчанию, текст, кнопка, раздел приложения)
CAMPAIGNS = {
    "no_server_24h": ("Не купил сервер — через 24 ч", 24,
                      "⚡️ <b>Your farm is still empty</b>\n\nYour first server is <b>25% off</b> — from 3 TON. "
                      "Rent it and start collecting TON CRY every day.", "🛒 Open Shop", "shop"),
    "no_server_72h": ("Не купил сервер — через 72 ч", 72,
                      "🖥 <b>Fresh servers every day</b>\n\nThe shop restocks daily at 12:00 MSK, and your 25% first-server "
                      "discount is still waiting for you.", "🛒 See servers", "shop"),
    "cheap_only_3d": ("Только дешёвые серверы — через 3 дня после покупки", 72,
                      "🚀 <b>Ready to grow your farm?</b>\n\nUpgrade your server to the next plan or rent a more powerful one. "
                      "Upgrades keep your rental term.", "⚙️ My servers", "myservers"),
}
CHEAP_TIERS = 1  # «дешёвые» — тарифы 0–1 (1 vCPU)


def cfg(key) -> dict:
    title, delay, text, btn, page = CAMPAIGNS[key]
    try:
        saved = json.loads(db.get_setting(f"promo_{key}", "{}"))
    except ValueError:
        saved = {}
    return {"key": key, "title": title, "enabled": saved.get("enabled", True), "delay_h": float(saved.get("delay_h", delay)),
            "text": saved.get("text") or text, "button": saved.get("button") or btn, "page": page,
            "sent": db.promo_count(key)}


def all_cfg() -> list:
    return [cfg(k) for k in CAMPAIGNS]


def save(key, **f):
    cur = cfg(key)
    data = {k: f.get(k, cur[k]) for k in ("enabled", "delay_h", "text", "button")}
    db.set_setting(f"promo_{key}", json.dumps(data, ensure_ascii=False))


def markup(c) -> InlineKeyboardMarkup:
    url = WEBAPP_URL.rstrip("/") + "/" + (f"?p={c['page']}" if c["page"] else "")
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=c["button"], web_app=WebAppInfo(url=url))],
                                                 [InlineKeyboardButton(text="🔕 Stop reminders", callback_data="promo:off")]])


def _quiet_now() -> bool:
    h = datetime.now(MSK).hour
    return not 10 <= h < 22


def eligible(key, delay_h, now) -> list[int]:
    cutoff = now - delay_h * 3600
    if key.startswith("no_server"):
        return db.promo_no_server(key, cutoff, now - 86400)
    if key == "cheap_only_3d":
        return db.promo_cheap_only(key, cutoff, now - 86400, CHEAP_TIERS)
    return []


async def tick(bot):
    """Вызывается из фонового цикла раз в минуту."""
    if _quiet_now():
        return
    now = time.time()
    for key in CAMPAIGNS:
        c = cfg(key)
        if not c["enabled"]:
            continue
        for uid in eligible(key, c["delay_h"], now)[:50]:
            if not db.promo_mark(uid, key):  # отмечаем заранее — не отправим дважды
                continue
            try:
                await bot.send_message(uid, c["text"], reply_markup=markup(c))
            except Exception:
                pass
            await asyncio.sleep(0.05)
