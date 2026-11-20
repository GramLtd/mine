import asyncio
import logging
import secrets
import time
from pathlib import Path

from aiogram.types import LabeledPrice
from fastapi import FastAPI, Depends, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import db, game, settings, ton
from .auth import current_user
from .config import (SERVERS, RENT_DAYS, DAILY_BONUS, CHANNEL_USERNAME, REF_BONUS_COINS, SHOP, STORAGE_ITEMS,
                     ADMIN_IDS, ADMIN_USERNAMES, WEBAPP_URL, TOPUP_MIN)

WEB = Path(__file__).resolve().parent.parent / "webapp"
ADMIN_UI = Path(__file__).resolve().parent / "admin_ui"  # не публикуется как статика
api = FastAPI()
bot = None  # выставляется из main.py
log = logging.getLogger("toncry")


def is_admin(tg) -> bool:
    return tg["id"] in ADMIN_IDS or (tg.get("username") or "").lower() in ADMIN_USERNAMES


def load(tg):
    name = tg.get("first_name", "") or tg.get("username", "")
    user, _ = db.get_or_create(tg["id"], name, username=tg.get("username"))
    if user.get("banned") and not is_admin(tg):
        raise HTTPException(403, {"banned": True, "support": settings.support(),
                                  "message": "Аккаунт заблокирован"})
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


@api.get("/api/friends")
def friends(tg=Depends(current_user)):
    user = load(tg)
    uname = getattr(api.state, "bot_username", "your_bot")
    return {"friends": db.friends(user["id"]), "bonus_per_friend": REF_BONUS_COINS,
            "link": f"https://t.me/{uname}?start=ref{user['id']}"}


@api.get("/api/missions")
def missions(tg=Depends(current_user)):
    user = load(tg)
    done = db.mission_done_ids(user["id"])
    return {"missions": [
        {"id": "daily", "title": "Ежедневный бонус", "reward": DAILY_BONUS,
         "done": time.time() - user["last_daily"] < 86400},
        *([{"id": "channel", "title": f"Подписка на {CHANNEL_USERNAME}",
            "reward": DAILY_BONUS * 5, "done": bool(user["channel_done"]),
            "url": f"https://t.me/{CHANNEL_USERNAME.lstrip('@')}"}] if CHANNEL_USERNAME else []),
        *[{"id": f"m{m['id']}", "title": m["title"], "reward": m["reward"], "url": m["url"],
           "done": m["id"] in done} for m in db.missions_list()],
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
    elif mid.startswith("m") and mid[1:].isdigit():
        m = db.mission_get(int(mid[1:]))
        if not m or not m["active"]:
            raise HTTPException(404, "Задание не найдено")
        if m["chat"]:
            try:
                member = await bot.get_chat_member(m["chat"], user["id"])
            except Exception:
                raise HTTPException(400, "Не удалось проверить подписку")
            if member.status in ("left", "kicked"):
                raise HTTPException(400, "Вы не подписаны")
        if not db.mission_complete(user["id"], m["id"]):
            raise HTTPException(400, "Уже выполнено")
        db.add_balance(user["id"], m["reward"])
    else:
        raise HTTPException(404)
    return {"ok": True}


class SkinIn(BaseModel):
    skin: str


@api.post("/api/skin")
def set_skin(body: SkinIn, tg=Depends(current_user)):
    user = load(tg)
    if body.skin and body.skin not in (user.get("skins") or "").split(","):
        raise HTTPException(400, "Скин не куплен")
    db.update(user["id"], skin=body.skin)
    return game.state(load(tg), is_admin(tg))


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


# ---------- покупки: баланс / TON / Stars ----------
class InvoiceIn(BaseModel):
    item: str
    amount: float | None = None  # только для пополнения


def _checked(user, item):
    try:
        game.check(user, item)
    except game.NotBuyable as e:
        raise HTTPException(400, str(e))


@api.post("/api/buy")
def buy_balance(body: InvoiceIn, tg=Depends(current_user)):
    """Оплата с баланса (1 монета = 1 TON)."""
    user = load(tg)
    if body.item == "topup":
        raise HTTPException(400, "Нет такого товара")
    _checked(user, body.item)
    price = game.price_ton(user, body.item)
    if not db.spend(user["id"], price):
        raise HTTPException(400, "Недостаточно средств на балансе")
    err = game.apply_item(user["id"], body.item, paid_ton=price)
    if err:
        raise HTTPException(400, err)
    return game.state(load(tg), is_admin(tg))


@api.post("/api/stars/invoice")
async def stars_invoice(body: InvoiceIn, tg=Depends(current_user)):
    user = load(tg)
    if body.item == "topup":
        raise HTTPException(400, "Пополнение — только в TON")
    _checked(user, body.item)
    stars = game.price_stars(user, body.item)
    title = game.item_title(body.item)[:32]
    link = await bot.create_invoice_link(
        title=title, description=title, payload=f"{body.item}|{user['id']}|{stars}",
        currency="XTR", prices=[LabeledPrice(label=title, amount=stars)], provider_token="")
    return {"link": link}


async def ton_paid(order):
    uid, amount = order["user_id"], order["nano"] / ton.NANO
    title = game.item_title(order["item"])
    if order["item"] == "topup":
        db.add_balance(uid, amount)
        err = None
    else:
        err = game.apply_item(uid, order["item"], paid_ton=amount)
    text = f"⚠️ {err}" if err else f"✅ Оплата {amount:g} TON получена — «{title}»."
    try:
        await bot.send_message(uid, text)
    except Exception:
        pass
    for aid in ADMIN_IDS:
        try:
            await bot.send_message(aid, f"💎 TON-оплата #{order['id']}: {amount:g} TON · {title} · id {uid}")
        except Exception:
            pass


@api.post("/api/ton/order")
def ton_order(body: InvoiceIn, tg=Depends(current_user)):
    user = load(tg)
    if not settings.ton_enabled():
        raise HTTPException(400, "Оплата в TON временно недоступна")
    item = body.item
    if item == "topup":
        amount = round(body.amount or 0, 4)
        if amount < TOPUP_MIN or amount > 100000:
            raise HTTPException(400, f"Минимальное пополнение — {TOPUP_MIN:g} TON")
    else:
        _checked(user, item)
        amount = game.price_ton(user, item)
    nano = round(amount * ton.NANO)
    comment = f"TC{user['id']}-{secrets.token_hex(3)}"
    oid = db.ton_order_create(user["id"], item, nano, comment)
    wallet = settings.ton_wallet()
    return {"id": oid, "address": wallet, "amount": nano / ton.NANO, "nano": nano, "comment": comment,
            "title": game.item_title(item), "payload": ton.comment_payload(comment),
            "bot": getattr(api.state, "bot_username", ""), **ton.transfer_links(wallet, nano, comment)}


@api.post("/api/ton/order/{oid}/check")
async def ton_order_check(oid: int, tg=Depends(current_user)):
    user = load(tg)
    o = db.ton_order_get(oid)
    if not o or o["user_id"] != user["id"]:
        raise HTTPException(404, "Заказ не найден")
    if o["status"] == "pending":
        try:
            await ton.check_payments(ton_paid)
        except Exception as e:
            log.warning("TON check failed: %s", e)
        o = db.ton_order_get(oid)
    return {"status": o["status"], **game.state(load(tg), is_admin(tg))}


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
    banned: bool | None = None
    boost_hours: float | None = None
    boost_mult: float | None = None
    add_balance: float | None = None


@api.post("/api/admin/users/{uid}")
def a_edit(uid: int, body: UserEdit, _=Depends(admin)):
    user = db.get(uid)
    if not user:
        raise HTTPException(404, "Пользователь не найден")
    game.settle(user)
    f = {}
    if body.balance is not None:
        f["balance"] = max(0.0, body.balance)
    if body.banned is not None:
        f["banned"] = int(body.banned)
    if body.boost_hours is not None:
        f["boost_until"] = time.time() + body.boost_hours * 3600
        f["boost_mult"] = body.boost_mult or 2
    if body.add_balance:
        f["balance"] = max(0.0, f.get("balance", db.get(uid)["balance"]) + body.add_balance)
    if f:
        db.update(uid, **f)
    return db.get(uid)


class GrantIn(BaseModel):
    item: str
    notify: bool = True


@api.post("/api/admin/users/{uid}/grant")
async def a_grant(uid: int, body: GrantIn, _=Depends(admin)):
    if not db.get(uid):
        raise HTTPException(404, "Пользователь не найден")
    if not (body.item in SHOP or body.item == "nofee" or body.item.startswith("srv:")):
        raise HTTPException(400, "Нет такого товара")
    if body.item.startswith("srv:"):  # выдача сервера не тратит склад
        game.settle(db.get(uid))
        db.server_add(uid, int(body.item[4:]), RENT_DAYS)
    else:
        game.apply_item(uid, body.item)
    if body.notify:
        try:
            await bot.send_message(uid, f"🎁 Вам выдано: «{game.item_title(body.item)}»")
        except Exception:
            pass
    u = db.get(uid)
    u["friends"] = db.friend_count(uid)
    return u


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
    support_username: str | None = None
    ton_wallet: str | None = None
    star_rub: float | None = None
    nofee_price: float | None = None
    stock_daily: list[int] | None = None
    ton_rub: float | None = None


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
    if body.support_username is not None:
        u = body.support_username.strip().lstrip("@").removeprefix("https://t.me/")
        if u and not (5 <= len(u) <= 32 and u.replace("_", "").isalnum()):
            raise HTTPException(400, "Неверный username поддержки")
        db.set_setting("support_username", u)
    if body.ton_wallet is not None:
        w = body.ton_wallet.strip()
        if w and not ton.valid_address(w):
            raise HTTPException(400, "Неверный TON-адрес кошелька для оплат")
        db.set_setting("ton_wallet", w)
    if body.star_rub is not None:
        if body.star_rub <= 0:
            raise HTTPException(400, "Цена звезды должна быть больше 0")
        db.set_setting("star_rub", body.star_rub)
    if body.nofee_price is not None:
        db.set_setting("nofee_price", max(0.01, body.nofee_price))
    if body.stock_daily is not None:
        for t, n in enumerate(body.stock_daily[:len(SERVERS)]):
            db.set_setting(f"stock_daily_{t}", max(0, int(n)))
    if body.ton_rub is not None:
        if body.ton_rub <= 0:
            raise HTTPException(400, "Курс TON должен быть больше 0")
        db.set_setting("ton_rub", body.ton_rub)
    return settings.all_settings()


class MissionIn(BaseModel):
    title: str
    url: str
    chat: str = ""      # @канал для проверки подписки (бот должен быть админом), можно пусто
    reward: float


@api.get("/api/admin/missions")
def a_missions(_=Depends(admin)):
    counts = db.mission_counts()
    return {"missions": [{**m, "done_count": counts.get(m["id"], 0)} for m in db.missions_list(False)]}


@api.post("/api/admin/missions")
def a_mission_add(body: MissionIn, _=Depends(admin)):
    if not body.title.strip() or not body.url.startswith(("https://", "http://")) or body.reward <= 0:
        raise HTTPException(400, "Заполните название, ссылку (https://…) и награду")
    return {"id": db.mission_add(body.title.strip(), body.url.strip(), body.chat.strip(), body.reward)}


@api.post("/api/admin/missions/{mid}/toggle")
def a_mission_toggle(mid: int, _=Depends(admin)):
    m = db.mission_get(mid)
    if not m:
        raise HTTPException(404)
    db.mission_set_active(mid, not m["active"])
    return {"ok": True}


# Интерфейс админки отдаётся только админам — у обычных игроков его нет даже в коде страницы.
@api.get("/api/admin/ui")
def a_ui(_=Depends(admin)):
    return {"html": (ADMIN_UI / "admin.html").read_text(encoding="utf-8")}


# ---------- статика ----------
@api.get("/tonconnect-manifest.json")
def tonconnect_manifest():
    base = WEBAPP_URL.rstrip("/")
    return {"url": base, "name": settings.coin() or "TonCry", "iconUrl": f"{base}/static/icon.png"}


@api.get("/")
def index():
    # Telegram сильно кеширует WebApp — без этого игроки видят старую версию после обновления
    return FileResponse(WEB / "index.html", headers={"Cache-Control": "no-store, must-revalidate"})


api.mount("/static", StaticFiles(directory=WEB), name="static")
