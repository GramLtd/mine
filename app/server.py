import asyncio
import html
import json
import logging
import secrets
import time
from pathlib import Path

from aiogram.types import LabeledPrice
from fastapi import FastAPI, Depends, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse, JSONResponse
from fastapi.exceptions import HTTPException as _HE
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import db, game, settings, ton, i18n
from .i18n import t, L
from .auth import current_user
from .config import (SERVERS, RENT_DAYS, DAILY_BONUS, CHANNEL_USERNAME, SHOP, STORAGE_ITEMS,
                     ADMIN_IDS, ADMIN_USERNAMES, WEBAPP_URL, TOPUP_MIN)

WEB = Path(__file__).resolve().parent.parent / "webapp"
ADMIN_UI = Path(__file__).resolve().parent / "admin_ui"  # не публикуется как статика
api = FastAPI()


# ---------- ограничение частоты запросов (защита от спама и перегрузки) ----------
_hits: dict = {}
LIMITS = [  # (префикс пути, запросов, за секунд)
    ("/check/", 40, 60),        # картинки чеков — тяжёлые для процессора
    ("/api/admin", 120, 60),
    ("/api/", 90, 60),
]


def _client_ip(request) -> str:
    # за nginx реальный адрес в X-Real-IP (см. deploy/nginx.conf)
    return request.headers.get("x-real-ip") or (request.client.host if request.client else "?")


@api.middleware("http")
async def rate_limit(request, call_next):
    path = request.url.path
    for prefix, n, per in LIMITS:
        if path.startswith(prefix):
            now = time.time()
            key = (_client_ip(request), prefix)
            q = [t for t in _hits.get(key, ()) if t > now - per]
            if len(q) >= n:
                return JSONResponse({"detail": t("Слишком много запросов, подождите немного")}, status_code=429)
            q.append(now)
            _hits[key] = q
            if len(_hits) > 50000:  # не даём словарю разрастись
                _hits.clear()
            break
    return await call_next(request)


@api.middleware("http")
async def lang_mw(request, call_next):
    """Язык интерфейса игрока: заголовок X-Lang (ru/en) от мини-приложения."""
    # игрокам — только английский; ответы админки (/api/admin) не переводятся
    i18n.lang_var.set(i18n.PLAYER_LANG)
    return await call_next(request)




@api.exception_handler(_HE)
async def translated_errors(request, exc: _HE):
    detail = exc.detail
    if isinstance(detail, str) and not request.url.path.startswith("/api/admin"):
        detail = t(detail)
    elif isinstance(detail, dict) and "message" in detail:
        detail = {**detail, "message": t(detail["message"])}
    return JSONResponse({"detail": detail}, status_code=exc.status_code, headers=getattr(exc, "headers", None))
bot = None  # выставляется из main.py
log = logging.getLogger("toncry")


def is_admin(tg) -> bool:
    # username можно сменить, и его займёт другой человек — поэтому, если заданы ADMIN_IDS, верим только им
    if ADMIN_IDS:
        return tg["id"] in ADMIN_IDS
    return (tg.get("username") or "").lower() in ADMIN_USERNAMES


def load(tg, allow_banned=False, allow_maintenance=False):
    name = tg.get("first_name", "") or tg.get("username", "")
    user, _ = db.get_or_create(tg["id"], name, username=tg.get("username"))
    if user.get("lang") != i18n.lang_var.get():  # запоминаем язык — на нём пишет бот
        db.update(user["id"], lang=i18n.lang_var.get())
        user["lang"] = i18n.lang_var.get()
    if settings.maintenance() and not allow_maintenance and not is_admin(tg):
        raise HTTPException(503, {"maintenance": True, "message": settings.maintenance_text()})
    if user.get("banned") and not allow_banned and not is_admin(tg):
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
    return {"friends": db.friends(user["id"]), "bonus_per_friend": settings.ref_bonus(),
            "link": f"https://t.me/{uname}?start=ref{user['id']}"}


@api.get("/api/missions")
async def missions(tg=Depends(current_user)):
    from . import botohub
    user = load(tg)
    done = db.mission_done_ids(user["id"])
    # спонсоры BotoHub: показываем ещё не награждённых (выполненных, но не забранных — тоже, чтобы забрать)
    got, sponsors = db.bh_rewarded(user["id"]), []
    for task in await botohub.tasks(user["id"]):
        if task["resource_id"] not in got:
            sponsors.append({"id": f"bh:{task['resource_id']}", "title": botohub.title(task["url"]), "reward": botohub.reward(),
                             "url": task["url"], "done": False, "sponsor": True})
    return {"missions": [*sponsors,
        {"id": "daily", "title": t("Ежедневный бонус"), "reward": DAILY_BONUS,
         "done": time.time() - user["last_daily"] < 86400},
        *[{"id": f"m{m['id']}", "title": m["title"], "reward": m["reward"], "url": m["url"],
           "done": m["id"] in done} for m in db.missions_list()],
    ]}


@api.post("/api/missions/{mid}")
async def do_mission(mid: str, tg=Depends(current_user)):
    user = load(tg)
    if mid == "daily":
        if not db.daily_take(user["id"], DAILY_BONUS):
            raise HTTPException(400, "Уже получено сегодня")
    elif mid.startswith("bh:"):
        from . import botohub
        rid = mid[3:]
        task = next((x for x in await botohub.tasks(user["id"]) if x["resource_id"] == rid), None)
        if not task:
            raise HTTPException(404, "Задание не найдено")
        if not task["completed"]:
            raise HTTPException(400, "Вы не подписаны")
        if not db.bh_reward(user["id"], rid, botohub.reward()):
            raise HTTPException(400, "Уже выполнено")
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


from .rules import REVISION as RULES_REV  # noqa: E402


def require_accepted(user):
    """Покупки и вывод — только после явного принятия правил и политики конфиденциальности."""
    if not user.get("accepted_at"):  # принял хоть раз — достаточно, повторно не спрашиваем
        raise HTTPException(403, "Сначала примите правила и политику конфиденциальности")


@api.post("/api/accept")
def accept_rules(tg=Depends(current_user)):
    user = load(tg)
    db.update(user["id"], accepted_at=time.time(), accepted_rev=RULES_REV)
    return game.state(load(tg), is_admin(tg))


@api.post("/api/tutorial")
def tutorial_done(tg=Depends(current_user)):
    db.update(load(tg)["id"], tutorial_done=1)
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
    require_accepted(user)
    if not settings.withdraw_enabled():
        raise HTTPException(400, "Вывод временно недоступен")
    address = body.address.strip()
    if not ton.valid_address(address):
        raise HTTPException(400, "Неверный TON-адрес")
    # выводятся только вознаграждения из призового фонда (в TON); TON CRY — игровая валюта и не выводится
    amount = round(body.amount, 4)
    if amount < settings.min_withdraw():
        raise HTTPException(400, f"Минимум {settings.min_withdraw():g} TON")
    wid = db.create_withdrawal(user["id"], amount, address)
    if wid is None:
        raise HTTPException(400, "Недостаточно вознаграждений или уже есть заявка в обработке")
    for aid in ADMIN_IDS:
        try:
            await bot.send_message(aid, f"💸 Вывод вознаграждения #{wid}: {amount:g} TON от "
                                        f"{html.escape(user['name'] or '')} (<code>{user['id']}</code>)\n<code>{html.escape(address)}</code>")
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
    """Оплата с баланса."""
    user = load(tg)
    require_accepted(user)
    if body.item == "topup":
        raise HTTPException(400, "Нет такого товара")
    _checked(user, body.item)
    price = game.price_ton(user, body.item)
    if not db.spend(user["id"], price):
        raise HTTPException(400, "Недостаточно средств на балансе")
    err = game.apply_item(user["id"], body.item, paid_ton=price)
    if err:
        raise HTTPException(400, err)
    db.balance_buy_log(user["id"], body.item, price)
    return game.state(load(tg), is_admin(tg))


@api.post("/api/stars/invoice")
async def stars_invoice(body: InvoiceIn, tg=Depends(current_user)):
    user = load(tg)
    require_accepted(user)
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
    from .bot import lang_of
    lg = lang_of(uid)
    text = f"⚠️ {t(err, lg)}" if err else L(lg, f"✅ Оплата {amount:g} TON получена — «{title}».",
                                              f"✅ Payment of {amount:g} TON received — “{t(title, 'en')}”.")
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
    require_accepted(user)
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
    # случайный код без Telegram ID: комментарий виден всем в блокчейне
    comment = "TC-" + secrets.token_hex(5)
    oid = db.ton_order_create(user["id"], item, nano, comment)
    wallet = settings.ton_wallet()
    return {"id": oid, "address": wallet, "amount": nano / ton.NANO, "nano": nano, "comment": comment,
            "title": t(game.item_title(item)), "payload": ton.comment_payload(comment),
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
    from . import rewards
    st = db.stats()
    rev = db.revenue_between(rewards.week_start(), time.time(), rewards.stars_to_ton(), ADMIN_IDS)
    return {**st, "week_revenue": rev, "week_fund": rev * rewards.share(), "reward_share": rewards.share()}


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
    game.rebase(user)
    f = {}
    if body.balance is not None:
        f["balance"] = max(0.0, body.balance)
    if body.banned is not None:
        f["banned"] = int(body.banned)
    if body.boost_hours is not None:
        f["boost_until"] = time.time() + body.boost_hours * 3600
        f["boost_mult"] = body.boost_mult or 2
    if f:
        db.update(uid, **f)
    if body.add_balance:  # атомарно, чтобы не затереть параллельные изменения баланса
        db.add_balance(uid, body.add_balance)
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
        if not body.item[4:].isdigit() or not 0 <= int(body.item[4:]) < len(SERVERS):
            raise HTTPException(400, "Нет такого сервера")
        game.rebase(db.get(uid))
        db.server_add(uid, int(body.item[4:]), RENT_DAYS)
    else:
        game.apply_item(uid, body.item)
    if body.notify:
        try:
            from .bot import lang_of
            lg = lang_of(uid)
            await bot.send_message(uid, L(lg, f"🎁 Вам выдано: «{game.item_title(body.item)}»",
                                          f"🎁 You received: “{t(game.item_title(body.item), 'en')}”"))
        except Exception:
            pass
    u = db.get(uid)
    u["friends"] = db.friend_count(uid)
    return u


class BcButton(BaseModel):
    text: str
    kind: str = "app"        # app | shop | myservers | friends | missions | rewards | url
    url: str | None = None
    same_row: bool = False   # в один ряд с предыдущей кнопкой


class Broadcast(BaseModel):
    text: str
    buttons: list[BcButton] = []
    test: bool = False       # отправить только себе — проверить, как выглядит


APP_PAGES = {"app": "", "shop": "shop", "myservers": "myservers", "friends": "friends", "missions": "missions", "rewards": "rewards"}


def _bc_markup(buttons):
    """Кнопки рассылки: открыть приложение (в т. ч. сразу нужный раздел) или внешняя ссылка."""
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
    rows = []
    for b in buttons[:12]:
        text = b.text.strip()[:64]
        if not text:
            raise HTTPException(400, "У кнопки нет текста")
        if b.kind == "url":
            url = (b.url or "").strip()
            if not url.startswith(("https://", "http://", "tg://")):
                raise HTTPException(400, f"Кнопка «{text}»: ссылка должна начинаться с https://")
            btn = InlineKeyboardButton(text=text, url=url)
        elif b.kind in APP_PAGES:
            page = APP_PAGES[b.kind]
            btn = InlineKeyboardButton(text=text, web_app=WebAppInfo(url=WEBAPP_URL.rstrip("/") + "/" + (f"?p={page}" if page else "")))
        else:
            raise HTTPException(400, "Неизвестный тип кнопки")
        if b.same_row and rows and len(rows[-1]) < 4:
            rows[-1].append(btn)
        else:
            rows.append([btn])
    return InlineKeyboardMarkup(inline_keyboard=rows) if rows else None


async def _broadcast(text: str, admin_id: int, markup=None):
    ok = fail = 0
    for uid in db.all_ids():
        try:
            await bot.send_message(uid, text, reply_markup=markup)
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
    markup = _bc_markup(body.buttons)
    if body.test:  # только себе: сразу видно ошибки разметки
        try:
            await bot.send_message(tg["id"], body.text, reply_markup=markup)
        except Exception as e:
            raise HTTPException(400, f"Telegram не принял сообщение: {e}")
        return {"ok": True, "recipients": 1}
    asyncio.create_task(_broadcast(body.text, tg["id"], markup))
    return {"ok": True, "recipients": len(db.all_ids())}


class TestMark(BaseModel):
    method: str
    ref: str
    test: bool


@api.post("/api/admin/payments/test")
def a_payment_test(body: TestMark, _=Depends(admin)):
    """Пометить платёж тестовым — он не пойдёт в призовой фонд."""
    if not db.payment_set_test(body.method, body.ref, body.test):
        raise HTTPException(404, "Платёж не найден")
    return {"ok": True}


@api.get("/api/admin/payments")
def a_payments(_=Depends(admin)):
    rows = db.all_payments()
    for r in rows:
        r["admin"] = r["user_id"] in ADMIN_IDS
        try:
            r["title"] = game.item_title(r["item"])
        except Exception:
            r["title"] = r["item"]
    return {"payments": rows}


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
    reason: str | None = None        # комментарий при отклонении — уходит игроку
    save_template: bool = False


@api.post("/api/admin/withdrawals/{wid}")
async def a_wd_action(wid: int, body: WdAction, _=Depends(admin)):
    if body.action not in ("paid", "rejected"):
        raise HTTPException(400, "Неизвестное действие")
    reason = (body.reason or "").strip()[:1000] or None
    w = db.finish_withdrawal(wid, body.action, body.tx, reason if body.action == "rejected" else None)
    if not w:
        raise HTTPException(400, "Заявка не найдена или уже обработана")
    if reason and body.save_template:
        tpl = settings.reject_templates()
        if reason not in tpl:
            db.set_setting("reject_templates", json.dumps(([reason] + tpl)[:30], ensure_ascii=False))
    from .bot import lang_of
    lg, coin, amt = lang_of(w["user_id"]), settings.coin(), w["amount"]
    if body.action == "paid":
        text = L(lg, f"✅ Вывод {amt:g} {coin} отправлен на ваш TON-кошелёк.", f"✅ Your withdrawal of {amt:g} {coin} has been sent to your TON wallet.")
        if body.tx:
            text += L(lg, "\nТранзакция: ", "\nTransaction: ") + f"https://tonviewer.com/transaction/{body.tx}"
    else:
        text = L(lg, f"↩️ Заявка на вывод {amt:g} {coin} отклонена, средства возвращены на баланс.",
                 f"↩️ Your withdrawal request for {amt:g} {coin} was declined, funds returned to your balance.")
        if reason:
            text += L(lg, "\n\n<b>Причина:</b> ", "\n\n<b>Reason:</b> ") + html.escape(reason)
    try:
        await bot.send_message(w["user_id"], text)
    except Exception:
        pass
    return {"ok": True}


@api.get("/api/admin/botohub_test")
async def a_botohub_test(tg=Depends(admin)):
    from . import botohub
    return await botohub.diagnose(tg["id"])


@api.get("/api/admin/promo")
def a_promo(_=Depends(admin)):
    from . import promo
    return {"campaigns": promo.all_cfg()}


class PromoIn(BaseModel):
    enabled: bool | None = None
    delay_h: float | None = None
    text: str | None = None
    button: str | None = None
    test: bool = False


@api.post("/api/admin/promo/{key}")
async def a_promo_save(key: str, body: PromoIn, tg=Depends(admin)):
    from . import promo
    if key not in promo.CAMPAIGNS:
        raise HTTPException(404)
    f = {k: v for k, v in body.model_dump().items() if v is not None and k != "test"}
    if "delay_h" in f:
        f["delay_h"] = max(1.0, min(24 * 30, f["delay_h"]))
    if "text" in f and not f["text"].strip():
        raise HTTPException(400, "Пустой текст")
    if "button" in f:
        f["button"] = f["button"].strip()[:64] or promo.CAMPAIGNS[key][3]
    promo.save(key, **f)
    c = promo.cfg(key)
    if body.test:
        try:
            await bot.send_message(tg["id"], c["text"], reply_markup=promo.markup(c))
        except Exception as e:
            raise HTTPException(400, f"Telegram не принял сообщение: {e}")
    return {"campaigns": promo.all_cfg()}


@api.get("/api/admin/reject_templates")
def a_tpl_list(_=Depends(admin)):
    return {"templates": settings.reject_templates()}


class TplIn(BaseModel):
    text: str


@api.post("/api/admin/reject_templates")
def a_tpl_add(body: TplIn, _=Depends(admin)):
    tx = body.text.strip()[:1000]
    if not tx:
        raise HTTPException(400, "Пустой шаблон")
    tpl = [x for x in settings.reject_templates() if x != tx]
    db.set_setting("reject_templates", json.dumps(([tx] + tpl)[:30], ensure_ascii=False))
    return {"templates": settings.reject_templates()}


@api.post("/api/admin/reject_templates/delete")
def a_tpl_del(body: TplIn, _=Depends(admin)):
    db.set_setting("reject_templates", json.dumps([x for x in settings.reject_templates() if x != body.text], ensure_ascii=False))
    return {"templates": settings.reject_templates()}


@api.get("/api/admin/settings")
def a_get_settings(_=Depends(admin)):
    return settings.all_settings()


class SettingsIn(BaseModel):
    coin_name: str | None = None
    welcome_text: str | None = None
    welcome_text_en: str | None = None
    min_withdraw: float | None = None
    withdraw_enabled: bool | None = None
    support_username: str | None = None
    ton_wallet: str | None = None
    star_rub: float | None = None
    nofee_price: float | None = None
    botohub_enabled: bool | None = None
    botohub_reward: float | None = None
    maintenance: bool | None = None
    maintenance_text: str | None = None
    reward_share: float | None = None
    reward_cap: float | None = None
    accrual_speed: float | None = None
    ref_bonus: float | None = None
    stock_daily: list[int] | None = None
    ton_rub: float | None = None


@api.post("/api/admin/settings")
def a_set_settings(body: SettingsIn, _=Depends(admin)):
    if body.coin_name is not None:
        name = body.coin_name.strip()
        if not 1 <= len(name) <= 16:
            raise HTTPException(400, "Название монеты: 1–16 символов")
        if not settings.coin_name_allowed(name):
            raise HTTPException(400, "TON CRY — игровая валюта: нельзя называть её как реальную криптовалюту (TON, GRAM и т. п.)")
        db.set_setting("coin_name", name)
    if body.welcome_text is not None:
        if not body.welcome_text.strip() or len(body.welcome_text) > 3500:
            raise HTTPException(400, "Текст приветствия: от 1 до 3500 символов")
        db.set_setting("welcome_text", body.welcome_text)
    if body.welcome_text_en is not None:
        if len(body.welcome_text_en) > 3500:
            raise HTTPException(400, "Текст приветствия: от 1 до 3500 символов")
        db.set_setting("welcome_text_en", body.welcome_text_en)
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
    if body.ref_bonus is not None:
        db.set_setting("ref_bonus", max(0.0, body.ref_bonus))
    if body.botohub_enabled is not None:
        db.set_setting("botohub_enabled", "1" if body.botohub_enabled else "0")
    if body.botohub_reward is not None:
        db.set_setting("botohub_reward", max(0.0, body.botohub_reward))
    if body.maintenance is not None:
        db.set_setting("maintenance", "1" if body.maintenance else "0")
    if body.maintenance_text is not None:
        db.set_setting("maintenance_text", body.maintenance_text.strip()[:1000])
    if body.reward_share is not None:  # доля недельной выручки в призовом фонде, не больше 50%
        db.set_setting("reward_share", min(0.5, max(0.0, body.reward_share)))
    if body.reward_cap is not None:
        db.set_setting("reward_cap", max(0.0, body.reward_cap))
    if body.accrual_speed is not None:  # множитель скорости начисления TON CRY (1 = как в таблице, до 3)
        from .config import ACCRUAL_MAX
        db.set_setting("accrual_speed", min(ACCRUAL_MAX, max(0.0, body.accrual_speed)))
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
def _rub(amount: float) -> str:
    try:
        return f"{amount * settings.ton_rub():,.0f}".replace(",", " ")
    except Exception:
        return ""


@api.get("/check/{amount}.jpg")
def check_image(amount: str, thumb: int = 0, n: int = 1):
    from fastapi import Response
    from . import checkimg
    try:
        a = float(amount)
        assert 0 < a <= 10_000_000
    except (ValueError, AssertionError):
        raise HTTPException(404)
    txt = f"{a:g}"
    n = max(1, min(n, 1000))
    data = checkimg.thumb(txt, settings.coin()) if thumb else checkimg.render(txt, settings.coin(), _rub(a), n)
    return Response(data, media_type="image/jpeg", headers={"Cache-Control": "public, max-age=86400"})


@api.get("/api/doc/{doc}")
def get_doc(doc: str):
    from . import rules
    if doc not in ("rules", "privacy"):
        raise HTTPException(404)
    return {"html": rules.text("en", getattr(api.state, "bot_username", ""), doc), "revision": rules.REVISION}


# ---------- поддержка из приложения ----------
class SupportIn(BaseModel):
    text: str


@api.get("/api/support")
def my_support(tg=Depends(current_user)):  # поддержка доступна и заблокированным, и во время техработ
    return {"messages": db.ticket_messages_for_user(load(tg, allow_banned=True, allow_maintenance=True)["id"])}


@api.post("/api/support")
async def send_support(body: SupportIn, tg=Depends(current_user)):
    from . import support
    user = load(tg, allow_banned=True, allow_maintenance=True)
    text = body.text.strip()
    if not 1 <= len(text) <= 2000:
        raise HTTPException(400, "Пустое сообщение")
    await support.from_user(bot, user, text)
    return {"messages": db.ticket_messages_for_user(user["id"])}


@api.get("/api/admin/tickets")
def a_tickets(status: str = "open", _=Depends(admin)):
    return {"tickets": db.tickets("closed" if status == "closed" else "open")}


@api.get("/api/admin/tickets/{tid}")
def a_ticket(tid: int, _=Depends(admin)):
    t = db.ticket_get(tid)
    if not t:
        raise HTTPException(404, "Обращение не найдено")
    return t


@api.post("/api/admin/tickets/{tid}/reply")
async def a_ticket_reply(tid: int, body: SupportIn, _=Depends(admin)):
    from . import support
    if not body.text.strip():
        raise HTTPException(400, "Пустое сообщение")
    if not await support.from_admin(bot, tid, body.text.strip()):
        raise HTTPException(400, "Не удалось отправить ответ")
    return db.ticket_get(tid)


@api.post("/api/admin/tickets/{tid}/close")
async def a_ticket_close(tid: int, _=Depends(admin)):
    from . import support
    await support.close(bot, tid)
    return {"ok": True}


@api.get("/tonconnect-manifest.json")
def tonconnect_manifest():
    base = WEBAPP_URL.rstrip("/")
    return {"url": base, "name": settings.coin() or "TonCry", "iconUrl": f"{base}/static/icon.png"}


@api.get("/")
def index():
    # Telegram сильно кеширует WebApp — без этого игроки видят старую версию после обновления
    return FileResponse(WEB / "index.html", headers={"Cache-Control": "no-store, must-revalidate"})


api.mount("/static", StaticFiles(directory=WEB), name="static")
