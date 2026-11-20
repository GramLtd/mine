from aiogram import Router, F
from aiogram.filters import CommandStart, CommandObject, Command
import html
import re
import secrets

from aiogram.types import (Message, InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo,
                           PreCheckoutQuery, InlineQuery, InlineQueryResultArticle, InputTextMessageContent,
                           InlineQueryResultsButton, ChosenInlineResult, CallbackQuery, InlineQueryResultPhoto)

from . import db, game, settings
from .config import WEBAPP_URL, SHOP, ADMIN_IDS, ADMIN_USERNAMES

router = Router()


def is_admin(u) -> bool:
    return u.id in ADMIN_IDS or (u.username or "").lower() in ADMIN_USERNAMES


def kb():
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="Открыть TonCry", web_app=WebAppInfo(url=WEBAPP_URL))
    ]])


@router.message(CommandStart())
async def start(msg: Message, command: CommandObject):
    ref = None
    if command.args and command.args.startswith("ref"):
        try:
            ref = int(command.args[3:])
        except ValueError:
            pass
    user, created = db.get_or_create(msg.from_user.id, msg.from_user.first_name, ref,
                                     username=msg.from_user.username)
    if created and user["referrer"]:
        try:
            await msg.bot.send_message(
                user["referrer"],
                f"👋 {msg.from_user.first_name} присоединился по вашей ссылке! Вы получите "
                f"+{settings.ref_bonus():g} {settings.coin()}, когда он арендует первый сервер.")
        except Exception:
            pass
    if user.get("banned") and not is_admin(msg.from_user):
        sup = settings.support()
        await msg.answer("⛔️ <b>Ваш аккаунт заблокирован.</b>\n\n" +
                         (f"Для разблокировки обратитесь в техподдержку: @{sup}" if sup
                          else "Для разблокировки обратитесь в техподдержку."),
                         reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(
                             text="Написать в поддержку", url=f"https://t.me/{sup}")]]) if sup else None)
        return
    try:
        await msg.answer(settings.welcome(), reply_markup=kb())
    except Exception:  # некорректный HTML в тексте — отправляем без разметки
        await msg.answer(settings.welcome(), reply_markup=kb(), parse_mode=None)


@router.message(Command("admin"))
async def admin_cmd(msg: Message):
    if not is_admin(msg.from_user):
        return
    s = db.stats()
    await msg.answer(
        f"<b>Админ-панель</b>\n\n"
        f"👥 Пользователей: {s['users']} (+{s['new_24h']} за 24ч)\n"
        f"⚡ Активных за 24ч: {s['active_24h']}\n"
        f"⭐ Stars: {s['stars_total']} (за 24ч: {s['stars_24h']})\n"
        f"🧾 Платежей: {s['payments']}\n"
        f"💸 Заявок на вывод: {s['wd_pending']}\n\n"
        f"Ваш ID: <code>{msg.from_user.id}</code> — добавьте его в ADMIN_IDS.\n"
        f"Полное управление — во вкладке «Админ» в приложении.",
        reply_markup=kb())


# ---------- Telegram Stars ----------
@router.pre_checkout_query()
async def pre_checkout(q: PreCheckoutQuery):
    item, uid, stars = (q.invoice_payload.split("|") + ["", ""])[:3]
    user = db.get(q.from_user.id)
    ok = bool(user) and not user.get("banned") and uid == str(q.from_user.id) and str(q.total_amount) == stars
    if ok:
        try:
            game.check(user, item)
        except game.NotBuyable as e:
            return await q.answer(ok=False, error_message=str(e))
    if ok:
        await q.answer(ok=True)
    else:
        await q.answer(ok=False, error_message="Не удалось оформить покупку, попробуйте ещё раз.")


@router.message(F.successful_payment)
async def paid(msg: Message):
    sp = msg.successful_payment
    pl = sp.invoice_payload
    item = pl.split("|")[0] if "|" in pl else pl.partition(":")[0]  # старый формат: item:uid
    err = None
    if db.add_payment(sp.telegram_payment_charge_id, msg.from_user.id, item, sp.total_amount):
        # если выдать уже нельзя (склад кончился) — возвращаем звёзды
        err = game.apply_item(msg.from_user.id, item)
        if err:
            try:
                await msg.bot.refund_star_payment(msg.from_user.id, sp.telegram_payment_charge_id)
                db.mark_refunded(sp.telegram_payment_charge_id)
                err += " Звёзды возвращены."
            except Exception:
                pass
    await msg.answer(f"⚠️ {err}" if err else f"⭐ Спасибо! «{game.item_title(item)}» — готово.", reply_markup=kb())


@router.message(Command("paysupport"))
async def paysupport(msg: Message):
    sup = settings.support()
    await msg.answer(f"По вопросам оплаты напишите в поддержку{': @' + sup if sup else ''}. Возврат Stars возможен по запросу.")


# ---------- чеки: @бот 1.5 в любом чате ----------
CHECK_MIN = 0.01


def _amount(text: str):
    m = re.fullmatch(r"\s*(\d+(?:[.,]\d{1,4})?)\s*(?:ton|тон)?\s*", text or "", re.I)
    return float(m.group(1).replace(",", ".")) if m else None


def _check_kb(cid, creator, amount):
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(
        text=f"💎 Получить {amount:g} {settings.coin()}", callback_data=f"c:{creator}:{round(amount * 10000)}:{cid}")]])


def _done_kb(text, bot_username):
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=text, url=f"https://t.me/{bot_username}")]])


@router.inline_query()
async def inline_check(q: InlineQuery):
    user = db.get(q.from_user.id)
    coin = settings.coin()
    open_btn = lambda t: InlineQueryResultsButton(text=t, start_parameter="checks")
    if not user or user.get("banned"):
        return await q.answer([], cache_time=0, is_personal=True, button=open_btn("Откройте бота, чтобы отправлять чеки"))
    bal = user["balance"]
    amount = _amount(q.query)
    if amount is None:
        return await q.answer([], cache_time=0, is_personal=True,
                              button=open_btn(f"Введите сумму чека · баланс {bal:.4f} {coin}"))
    if amount < CHECK_MIN:
        return await q.answer([], cache_time=0, is_personal=True, button=open_btn(f"Минимум {CHECK_MIN:g} {coin}"))
    if amount > bal:
        return await q.answer([], cache_time=0, is_personal=True,
                              button=open_btn(f"Недостаточно средств · баланс {bal:.4f} {coin}"))
    cid = secrets.token_hex(6)
    from .server import _rub
    rub = _rub(amount)
    caption = f"🎁 Чек на 💎 <b>{amount:g} {coin}</b>" + (f" (≈ {rub} ₽)" if rub else "") + "."
    base = WEBAPP_URL.rstrip("/")
    await q.answer([InlineQueryResultPhoto(
        id=cid, photo_url=f"{base}/check/{amount:g}.jpg", thumbnail_url=f"{base}/check/{amount:g}.jpg?thumb=1",
        photo_width=1280, photo_height=720, title=f"Чек на {amount:g} {coin}",
        description=f"Спишется с баланса · осталось {bal - amount:.4f}",
        caption=caption, parse_mode="HTML",
        reply_markup=_check_kb(cid, q.from_user.id, amount))], cache_time=0, is_personal=True)


@router.chosen_inline_result()
async def chosen_check(r: ChosenInlineResult):
    """Приходит, если в @BotFather включено /setinlinefeedback — тогда сумма резервируется сразу при отправке."""
    amount = _amount(r.query)
    if amount is None or not re.fullmatch(r"[0-9a-f]{12}", r.result_id):
        return
    status = db.check_reserve(r.result_id, r.from_user.id, amount)
    if status == "failed" and r.inline_message_id:
        try:
            me = await r.bot.me()
            await r.bot.edit_message_reply_markup(inline_message_id=r.inline_message_id,
                                                  reply_markup=_done_kb("❌ Недостаточно средств", me.username))
        except Exception:
            pass


@router.callback_query(F.data.startswith("c:"))
async def claim_check(cb: CallbackQuery):
    try:
        _, creator, amt, cid = cb.data.split(":")
        creator, amount = int(creator), int(amt) / 10000
    except ValueError:
        return await cb.answer()
    coin = settings.coin()
    me = await cb.bot.me()

    async def edit(label):  # меняем кнопку на «✅ Получено» со ссылкой на бота
        mk = _done_kb(label, me.username)
        if cb.inline_message_id:
            await cb.bot.edit_message_reply_markup(inline_message_id=cb.inline_message_id, reply_markup=mk)
        else:
            await cb.message.edit_reply_markup(reply_markup=mk)
    if cb.from_user.id == creator:
        if db.check_cancel(cid, creator, amount) == "ok":
            await cb.answer(f"Чек отменён, {amount:g} {coin} вернулись на баланс", show_alert=True)
            try:
                await edit(f"🚫 Отменён: {amount:g} {coin}")
            except Exception:
                pass
        else:
            await cb.answer("Чек уже недействителен", show_alert=True)
        return
    u, _ = db.get_or_create(cb.from_user.id, cb.from_user.first_name, username=cb.from_user.username)
    if u.get("banned"):
        return await cb.answer("Аккаунт заблокирован", show_alert=True)
    res = db.check_claim(cid, creator, amount, cb.from_user.id)
    if res == "ok":
        name = html.escape(cb.from_user.first_name or "")
        await cb.answer(f"+{amount:g} {coin} на баланс!", show_alert=True)
        try:
            await edit(f"✅ Получено: {amount:g} {coin}")
        except Exception:
            pass
        try:
            await cb.bot.send_message(creator, f"✅ {name} получил ваш чек на {amount:g} {coin}.")
        except Exception:
            pass
        try:
            await cb.bot.send_message(cb.from_user.id, f"💎 Вы получили чек на <b>{amount:g} {coin}</b>!", reply_markup=kb())
        except Exception:
            pass
    else:
        await cb.answer({"claimed": "Чек уже получен", "cancelled": "Чек отменён отправителем",
                         "failed": "Чек недействителен", "no_funds": "У отправителя недостаточно средств"}.get(res, "Чек недействителен"),
                        show_alert=True)
