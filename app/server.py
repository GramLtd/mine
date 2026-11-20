import asyncio
import logging
import time
from pathlib import Path

from aiogram.types import LabeledPrice
from fastapi import FastAPI, Depends, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import db, game, settings, ton
from .auth import current_user
from .config import (LEVELS, DAILY_BONUS, CHANNEL_USERNAME, REF_BONUS_COINS, SHOP,
                     ADMIN_IDS, ADMIN_USERNAMES)

WEB = Path(__file__).resolve().parent.parent / "webapp"
ADMIN_UI = Path(__file__).resolve().parent / "admin_ui"  # не публикуется как статика
api = FastAPI()
bot = None  # выставляется из main.py
log = logging.getLogger("hashfan")


def is_admin(tg) -> bool:
    return tg["id"] in ADMIN_IDS or (tg.get("username") or "").lower() in ADMIN_USERNAMES


def load(tg):
    name = tg.get("first_name", "") or tg.get("username", "")
    user, _ = db.get_or_create(tg["id"], name, username=tg.get("username"))
    if user.get("banned") and not is_admin(tg):
        raise HTTPException(403, "Аккаунт заблокирован")
    return user


def admin(tg=Depends(current_user)):
    if not is_admin(tg):
        raise HTTPException(403, "Нет доступа")
    return tg


# ---------- игра ----------
@api.get("/api/state")
def get_state(tg=Depends(current_user)):
    return game.state(load(tg), is_admin(tg))


@api.post("/api/claim")
def claim(tg=Depends(current_user)):
    amount = game.settle(load(tg))
    return {"claimed": amount, **game.state(load(tg), is_admin(tg))}


@api.post("/api/upgrade")
def upgrade(tg=Depends(current_user)):
    user = load(tg)
    if user["level"] + 1 >= len(LEVELS):
        raise HTTPException(400, "Максимальный уровень")
    price = LEVELS[user["level"] + 1][1]
    if user["balance"] < price:
        raise HTTPException(400, "Недостаточно монет")
    game.settle(user)
    db.update(user["id"], level=user["level"] + 1)
    db.add_balance(user["id"], -price)
    return game.state(load(tg), is_admin(tg))


@api.get("/api/friends")
def friends(tg=Depends(current_user)):
    user = load(tg)
    uname = getattr(api.state, "bot_username", "your_bot")
    return {"friends": db.friends(user["id"]), "bonus_per_friend": REF_BONUS_COINS,
            "link": f"https://t.me/{uname}?start=ref{user['id']}"}


@api.get("/api/missions")
def missions(tg=Depends(current_user)):
    user = load(tg)
    return {"missions": [
        {"id": "daily", "title": "Ежедневный бонус", "reward": DAILY_BONUS,
         "done": time.time() - user["last_daily"] < 86400},
        *([{"id": "channel", "title": f"Подписка на {CHANNEL_USERNAME}",
            "reward": DAILY_BONUS * 5, "done": bool(user["channel_done"]),
            "url": f"https://t.me/{CHANNEL_USERNAME.lstrip('@')}"}] if CHANNEL_USERNAME else []),
    ]}


@api.post("/api/missions/{mid}")
async def do_mission(mid: str, tg=Depends(current_user)):
    user = load(tg)
    if mid == "daily":
        if time.time() - user["last_daily"] < 86400:
            raise HTTPException(400, "Уже получено сегодня")
        db.update(user["id"], last_daily=time.time())
        db.add_balance(user["id"], DAILY_BONUS)
    elif mid == "channel" and CHANNEL_USERNAME:
        if user["channel_done"]:
            raise HTTPException(400, "Уже выполнено")
        member = await bot.get_chat_member(CHANNEL_USERNAME, user["id"])
        if member.status in ("left", "kicked"):
            raise HTTPException(400, "Вы не подписаны")
        db.update(user["id"], channel_done=1)
        db.add_balance(user["id"], DAILY_BONUS * 5)
    else:
        raise HTTPException(404)
    return {"ok": True}


# ---------- вывод ----------
class WithdrawIn(BaseModel):
    amount: float
    address: str


@api.get("/api/withdrawals")
def my_withdrawals(tg=Depends(current_user)):
    return {"withdrawals": db.withdrawals(uid=load(tg)["id"], limit=20)}


@api.post("/api/withdraw")
async def withdraw(body: WithdrawIn, tg=Depends(current_user)):
    user = load(tg)
    if not settings.withdraw_enabled():
        raise HTTPException(400, "Вывод временно недоступен")
    address = body.address.strip()
    if not ton.valid_address(address):
        raise HTTPException(400, "Неверный TON-адрес")
    amount = round(body.amount, 4)
    if amount < settings.min_withdraw():
        raise HTTPException(400, f"Минимум {settings.min_withdraw():g} {settings.coin()}")
    game.settle(user)
    wid = db.create_withdrawal(user["id"], amount, address)
    if wid is None:
        raise HTTPException(400, "Недостаточно средств или уже есть заявка в обработке")
    for aid in ADMIN_IDS:
        try:
            await bot.send_message(aid, f"💸 Заявка #{wid}: {amount:g} {settings.coin()} от "
                                        f"{user['name']} (<code>{user['id']}</code>)\n<code>{address}</code>")
        except Exception:
            pass
    return {"ok": True, "id": wid, **game.state(load(tg), is_admin(tg))}


# ---------- Telegram Stars ----------
class InvoiceIn(BaseModel):
    item: str


@api.post("/api/stars/invoice")
async def stars_invoice(body: InvoiceIn, tg=Depends(current_user)):
    user = load(tg)
    if body.item not in SHOP:
        raise HTTPException(404, "Нет такого товара")
    title, desc, price = SHOP[body.item]
    link = await bot.create_invoice_link(
        title=title, description=desc, payload=f"{body.item}:{user['id']}",
        currency="XTR", prices=[LabeledPrice(label=title, amount=price)], provider_token="")
    return {"link": link}


# ---------- Админка ----------
@api.get("/api/admin/stats")
def a_stats(_=Depends(admin)):
    return db.stats()


@api.get("/api/admin/users")
def a_users(q: str = "", _=Depends(admin)):
    users = db.search(q)
    for u in users:
        u["friends"] = db.friend_count(u["id"])
    return {"users": users}


class UserEdit(BaseModel):
    balance: float | None = None
    level: int | None = None   # 1..max
    banned: bool | None = None
    boost_hours: float | None = None
    boost_mult: float | None = None


@api.post("/api/admin/users/{uid}")
def a_edit(uid: int, body: UserEdit, _=Depends(admin)):
    user = db.get(uid)
    if not user:
        raise HTTPException(404, "Пользователь не найден")
    game.settle(user)
    f = {}
    if body.balance is not None:
        f["balance"] = max(0.0, body.balance)
    if body.level is not None:
        f["level"] = max(0, min(len(LEVELS) - 1, body.level - 1))
    if body.banned is not None:
        f["banned"] = int(body.banned)
    if body.boost_hours is not None:
        f["boost_until"] = time.time() + body.boost_hours * 3600
        f["boost_mult"] = body.boost_mult or 2
    if f:
        db.update(uid, **f)
    return db.get(uid)


class Broadcast(BaseModel):
    text: str


async def _broadcast(text: str, admin_id: int):
    ok = fail = 0
    for uid in db.all_ids():
        try:
            await bot.send_message(uid, text)
            ok += 1
        except Exception:
            fail += 1
        await asyncio.sleep(0.05)  # ~20 сообщений/с — в пределах лимитов Telegram
    try:
        await bot.send_message(admin_id, f"📣 Рассылка завершена: ✅ {ok}, ❌ {fail}")
    except Exception:
        pass


@api.post("/api/admin/broadcast")
async def a_broadcast(body: Broadcast, tg=Depends(admin)):
    if not body.text.strip():
        raise HTTPException(400, "Пустое сообщение")
    asyncio.create_task(_broadcast(body.text, tg["id"]))
    return {"ok": True, "recipients": len(db.all_ids())}


@api.get("/api/admin/payments")
def a_payments(_=Depends(admin)):
    return {"payments": db.payments()}


@api.post("/api/admin/refund/{charge_id}")
async def a_refund(charge_id: str, _=Depends(admin)):
    p = db.get_payment(charge_id)
    if not p or p["refunded"]:
        raise HTTPException(400, "Платёж не найден или уже возвращён")
    await bot.refund_star_payment(user_id=p["user_id"], telegram_payment_charge_id=charge_id)
    db.mark_refunded(charge_id)
    return {"ok": True}


@api.get("/api/admin/withdrawals")
def a_withdrawals(status: str = "pending", _=Depends(admin)):
    return {"withdrawals": db.withdrawals(status=status or None, limit=100)}


class WdAction(BaseModel):
    action: str          # paid | rejected
    tx: str | None = None


@api.post("/api/admin/withdrawals/{wid}")
async def a_wd_action(wid: int, body: WdAction, _=Depends(admin)):
    if body.action not in ("paid", "rejected"):
        raise HTTPException(400, "Неизвестное действие")
    w = db.finish_withdrawal(wid, body.action, body.tx)
    if not w:
        raise HTTPException(400, "Заявка не найдена или уже обработана")
    text = (f"✅ Вывод {w['amount']:g} {settings.coin()} отправлен на ваш TON-кошелёк."
            if body.action == "paid" else
            f"↩️ Заявка на вывод {w['amount']:g} {settings.coin()} отклонена, монеты возвращены на баланс.")
    if body.action == "paid" and body.tx:
        text += f"\nТранзакция: https://tonviewer.com/transaction/{body.tx}"
    try:
        await bot.send_message(w["user_id"], text)
    except Exception:
        pass
    return {"ok": True}


@api.get("/api/admin/settings")
def a_get_settings(_=Depends(admin)):
    return settings.all_settings()


class SettingsIn(BaseModel):
    coin_name: str | None = None
    welcome_text: str | None = None
    min_withdraw: float | None = None
    withdraw_enabled: bool | None = None


@api.post("/api/admin/settings")
def a_set_settings(body: SettingsIn, _=Depends(admin)):
    if body.coin_name is not None:
        name = body.coin_name.strip()
        if not 1 <= len(name) <= 16:
            raise HTTPException(400, "Название монеты: 1–16 символов")
        db.set_setting("coin_name", name)
    if body.welcome_text is not None:
        if not body.welcome_text.strip() or len(body.welcome_text) > 3500:
            raise HTTPException(400, "Текст приветствия: от 1 до 3500 символов")
        db.set_setting("welcome_text", body.welcome_text)
    if body.min_withdraw is not None:
        db.set_setting("min_withdraw", max(0.0001, body.min_withdraw))
    if body.withdraw_enabled is not None:
        db.set_setting("withdraw_enabled", "1" if body.withdraw_enabled else "0")
    return settings.all_settings()


# Интерфейс админки отдаётся только админам — у обычных игроков его нет даже в коде страницы.
@api.get("/api/admin/ui")
def a_ui(_=Depends(admin)):
    return {"html": (ADMIN_UI / "admin.html").read_text(encoding="utf-8")}


# ---------- статика ----------
@api.get("/")
def index():
    return FileResponse(WEB / "index.html")


api.mount("/static", StaticFiles(directory=WEB), name="static")
