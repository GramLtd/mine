from aiogram import Router, F
from aiogram.filters import CommandStart, CommandObject, Command
import html
import re
import secrets

from aiogram.types import (Message, InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo,
                           PreCheckoutQuery, InlineQuery, InlineQueryResultArticle, InputTextMessageContent,
                           InlineQueryResultsButton, ChosenInlineResult, CallbackQuery, InlineQueryResultPhoto)

from . import db, game, settings
from .i18n import L, t, norm
from .config import WEBAPP_URL, SHOP, ADMIN_IDS, ADMIN_USERNAMES

router = Router()


def is_admin(u) -> bool:
    if ADMIN_IDS:  # см. server.is_admin
        return u.id in ADMIN_IDS
    return (u.username or "").lower() in ADMIN_USERNAMES


def lang_of(uid, tg_user=None) -> str:
    """Язык игрока — бот для игроков работает только на английском."""
    return norm(None)


def kb(lang="ru"):
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=L(lang, "Открыть TonCry", "Open TonCry"), web_app=WebAppInfo(url=WEBAPP_URL))
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
    if not user.get("lang"):
        db.update(user["id"], lang=norm(msg.from_user.language_code))
    lang = lang_of(msg.from_user.id, msg.from_user)
    if created and user["referrer"]:
        rl = lang_of(user["referrer"])
        try:
            await msg.bot.send_message(
                user["referrer"], L(rl,
                f"👋 {html.escape(msg.from_user.first_name or '')} присоединился по вашей ссылке! Вы получите "
                f"+{settings.ref_bonus():g} {settings.coin()}, когда он арендует первый сервер.",
                f"👋 {html.escape(msg.from_user.first_name or '')} joined via your link! You'll get "
                f"+{settings.ref_bonus():g} {settings.coin()} when they rent their first server."))
        except Exception:
            pass
    if user.get("banned") and not is_admin(msg.from_user):
        sup = settings.support()
        await msg.answer(L(lang, "⛔️ <b>Ваш аккаунт заблокирован.</b>\n\n", "⛔️ <b>Your account is blocked.</b>\n\n") +
                         (L(lang, f"Для разблокировки обратитесь в техподдержку: @{sup}", f"Contact support to unblock: @{sup}") if sup
                          else L(lang, "Для разблокировки обратитесь в техподдержку.", "Contact support to unblock.")),
                         reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(
                             text=L(lang, "Написать в поддержку", "Contact support"), url=f"https://t.me/{sup}")]]) if sup else None)
        return
    try:
        await msg.answer(settings.welcome(lang), reply_markup=kb(lang))
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
            return await q.answer(ok=False, error_message=t(str(e), lang_of(q.from_user.id, q.from_user)))
    if ok:
        await q.answer(ok=True)
    else:
        await q.answer(ok=False, error_message=L(lang_of(q.from_user.id, q.from_user), "Не удалось оформить покупку, попробуйте ещё раз.", "Could not complete the purchase, please try again."))


@router.message(F.successful_payment)
async def paid(msg: Message):
    sp = msg.successful_payment
    pl = sp.invoice_payload
    item = pl.split("|")[0] if "|" in pl else pl.partition(":")[0]  # старый формат: item:uid
    err, refunded = None, False
    lang = lang_of(msg.from_user.id, msg.from_user)
    if db.add_payment(sp.telegram_payment_charge_id, msg.from_user.id, item, sp.total_amount):
        # если выдать уже нельзя (склад кончился) — возвращаем звёзды
        err = game.apply_item(msg.from_user.id, item)
        if err:
            try:
                await msg.bot.refund_star_payment(msg.from_user.id, sp.telegram_payment_charge_id)
                db.mark_refunded(sp.telegram_payment_charge_id)
                refunded = True
            except Exception:
                pass
    if err:
        text = f"⚠️ {t(err, lang)}" + (L(lang, " Звёзды возвращены.", " Stars refunded.") if refunded else "")
    else:
        text = L(lang, f"⭐ Спасибо! «{game.item_title(item)}» — готово.", f"⭐ Thank you! “{t(game.item_title(item), 'en')}” — done.")
    await msg.answer(text, reply_markup=kb(lang))


@router.message(Command("paysupport"))
async def paysupport(msg: Message):
    sup = settings.support()
    lang = lang_of(msg.from_user.id, msg.from_user)
    await msg.answer(L(lang, f"По вопросам оплаты напишите в поддержку{': @' + sup if sup else ''}. Возврат Stars возможен по запросу.",
                       f"For payment questions contact support{': @' + sup if sup else ''}. Stars refunds are available on request."))


# ---------- чеки: @бот 1.5 в любом чате ----------
CHECK_MIN = 0.01


MCHECK_MAX = 1000
_Q = re.compile(r"\s*(\d+(?:[.,]\d{1,4})?)\s*(?:ton|тон)?\s*(?:[xх×*]\s*(\d{1,4})\s*(?:шт|чел|pcs)?\.?)?\s*", re.I)


def _parse(text: str):
    """«1.5» → (1.5, 1); «0.5 x10» → (0.5, 10) — мультичек на 10 активаций."""
    m = _Q.fullmatch(text or "")
    if not m:
        return None, 1
    return float(m.group(1).replace(",", ".")), int(m.group(2) or 1)


def _amount(text: str):
    return _parse(text)[0]


def _check_kb(cid, creator, amount, lang="ru"):
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(
        text=L(lang, f"💎 Получить {amount:g} {settings.coin()}", f"💎 Claim {amount:g} {settings.coin()}"), callback_data=f"c:{creator}:{round(amount * 10000)}:{cid}")]])


def _done_kb(text, bot_username):
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=text, url=f"https://t.me/{bot_username}")]])


@router.inline_query()
async def inline_check(q: InlineQuery):
    user = db.get(q.from_user.id)
    coin = settings.coin()
    lang = lang_of(q.from_user.id, q.from_user)
    open_btn = lambda t: InlineQueryResultsButton(text=t, start_parameter="checks")
    if not user or user.get("banned"):
        return await q.answer([], cache_time=0, is_personal=True, button=open_btn(L(lang, "Откройте бота, чтобы отправлять чеки", "Open the bot to send checks")))
    bal = user["balance"]
    amount, n = _parse(q.query)
    if amount is None:
        return await q.answer([], cache_time=0, is_personal=True,
                              button=open_btn(L(lang, f"Сумма, или «0.5 x10» — мультичек · баланс {bal:.4f}", f"Amount, or “0.5 x10” for a multi-check · balance {bal:.4f}")))
    if amount < CHECK_MIN:
        return await q.answer([], cache_time=0, is_personal=True, button=open_btn(L(lang, f"Минимум {CHECK_MIN:g} {coin}", f"Minimum {CHECK_MIN:g} {coin}")))
    if not 1 <= n <= MCHECK_MAX:
        return await q.answer([], cache_time=0, is_personal=True, button=open_btn(L(lang, f"Активаций: от 1 до {MCHECK_MAX}", f"Activations: 1 to {MCHECK_MAX}")))
    total = round(amount * n, 4)
    if total > bal:
        return await q.answer([], cache_time=0, is_personal=True,
                              button=open_btn(L(lang, f"Недостаточно средств · нужно {total:g}, баланс {bal:.4f}", f"Insufficient funds · need {total:g}, balance {bal:.4f}")))
    from .server import _rub
    base = WEBAPP_URL.rstrip("/")
    if n == 1:
        cid = secrets.token_hex(6)
        rub = _rub(amount)
        caption = L(lang, f"🎁 Чек на 💎 <b>{amount:g} {coin}</b>" + (f" (≈ {rub} ₽)" if rub else "") + ".",
                    f"🎁 Check for 💎 <b>{amount:g} {coin}</b>.")
        res = InlineQueryResultPhoto(
            id=cid, photo_url=f"{base}/check/{amount:g}.jpg", thumbnail_url=f"{base}/check/{amount:g}.jpg?thumb=1",
            photo_width=1280, photo_height=720, title=L(lang, f"Чек на {amount:g} {coin}", f"Check for {amount:g} {coin}"),
            description=L(lang, f"Спишется с баланса · осталось {bal - amount:.4f}", f"Paid from balance · {bal - amount:.4f} left"),
            caption=caption, parse_mode="HTML", reply_markup=_check_kb(cid, q.from_user.id, amount, lang))
    else:
        cid = "m" + secrets.token_hex(6)[:11]
        caption = L(lang, f"🎁 Мультичек: 💎 <b>{amount:g} {coin}</b> каждому — для {n} человек.\nНажмите кнопку, чтобы получить.",
                    f"🎁 Multi-check: 💎 <b>{amount:g} {coin}</b> each — for {n} people.\nTap the button to claim.")
        res = InlineQueryResultPhoto(
            id=cid, photo_url=f"{base}/check/{amount:g}.jpg?n={n}", thumbnail_url=f"{base}/check/{amount:g}.jpg?thumb=1",
            photo_width=1280, photo_height=720,
            title=L(lang, f"Мультичек: {amount:g} {coin} × {n}", f"Multi-check: {amount:g} {coin} × {n}"),
            description=L(lang, f"Спишется {total:g} · осталось {bal - total:.4f}", f"{total:g} will be charged · {bal - total:.4f} left"),
            caption=caption, parse_mode="HTML", reply_markup=_mcheck_kb(cid, q.from_user.id, amount, n, 0, lang))
    await q.answer([res], cache_time=0, is_personal=True)


def _mcheck_kb(cid, creator, amount, total, claimed, lang="ru"):
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(
        text=L(lang, f"💎 Получить {amount:g} {settings.coin()} · {claimed}/{total}", f"💎 Claim {amount:g} {settings.coin()} · {claimed}/{total}"),
        callback_data=f"m:{creator}:{round(amount * 10000)}:{total}:{cid}")]])


@router.chosen_inline_result()
async def chosen_check(r: ChosenInlineResult):
    """Приходит, если в @BotFather включено /setinlinefeedback — тогда сумма резервируется сразу при отправке."""
    amount, n = _parse(r.query)
    if amount is None:
        return
    if re.fullmatch(r"m[0-9a-f]{11}", r.result_id) and n > 1:
        status = db.mcheck_reserve(r.result_id, r.from_user.id, amount, n)
    elif re.fullmatch(r"[0-9a-f]{12}", r.result_id):
        status = db.check_reserve(r.result_id, r.from_user.id, amount)
    else:
        return
    if status == "failed" and r.inline_message_id:
        try:
            me = await r.bot.me()
            await r.bot.edit_message_reply_markup(inline_message_id=r.inline_message_id,
                                                  reply_markup=_done_kb(L(lang_of(r.from_user.id, r.from_user), "❌ Недостаточно средств", "❌ Insufficient funds"), me.username))
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
    lc = lang_of(creator)                       # язык отправителя — для надписей на самом чеке
    lu = lang_of(cb.from_user.id, cb.from_user)  # язык нажавшего — для всплывающих ответов

    async def edit(label):  # меняем кнопку на «✅ Получено» со ссылкой на бота
        mk = _done_kb(label, me.username)
        if cb.inline_message_id:
            await cb.bot.edit_message_reply_markup(inline_message_id=cb.inline_message_id, reply_markup=mk)
        else:
            await cb.message.edit_reply_markup(reply_markup=mk)
    if cb.from_user.id == creator:
        if db.check_cancel(cid, creator, amount) == "ok":
            await cb.answer(L(lu, f"Чек отменён, {amount:g} {coin} вернулись на баланс", f"Check cancelled, {amount:g} {coin} returned to balance"), show_alert=True)
            try:
                await edit(L(lc, f"🚫 Отменён: {amount:g} {coin}", f"🚫 Cancelled: {amount:g} {coin}"))
            except Exception:
                pass
        else:
            await cb.answer(L(lu, "Чек уже недействителен", "This check is no longer valid"), show_alert=True)
        return
    u, _ = db.get_or_create(cb.from_user.id, cb.from_user.first_name, username=cb.from_user.username)
    if u.get("banned"):
        return await cb.answer(L(lu, "Аккаунт заблокирован", "Account blocked"), show_alert=True)
    res = db.check_claim(cid, creator, amount, cb.from_user.id)
    if res == "ok":
        name = html.escape(cb.from_user.first_name or "")
        await cb.answer(L(lu, f"+{amount:g} {coin} на баланс!", f"+{amount:g} {coin} added to your balance!"), show_alert=True)
        try:
            await edit(L(lc, f"✅ Получено: {amount:g} {coin}", f"✅ Received: {amount:g} {coin}"))
        except Exception:
            pass
        try:
            await cb.bot.send_message(creator, L(lc, f"✅ {name} получил ваш чек на {amount:g} {coin}.", f"✅ {name} claimed your check for {amount:g} {coin}."))
        except Exception:
            pass
        try:
            await cb.bot.send_message(cb.from_user.id, L(lu, f"💎 Вы получили чек на <b>{amount:g} {coin}</b>!", f"💎 You received a check for <b>{amount:g} {coin}</b>!"), reply_markup=kb(lu))
        except Exception:
            pass
    else:
        msgs = {"claimed": ("Чек уже получен", "Check already claimed"), "cancelled": ("Чек отменён отправителем", "Check cancelled by sender"),
                "failed": ("Чек недействителен", "Check is invalid"), "no_funds": ("У отправителя недостаточно средств", "Sender has insufficient funds")}
        ru_m, en_m = msgs.get(res, msgs["failed"])
        await cb.answer(L(lu, ru_m, en_m),
                        show_alert=True)


@router.callback_query(F.data.startswith("m:"))
async def claim_mcheck(cb: CallbackQuery):
    try:
        _, creator, amt, total, cid = cb.data.split(":")
        creator, amount, total = int(creator), int(amt) / 10000, int(total)
        assert re.fullmatch(r"m[0-9a-f]{11}", cid) and 1 < total <= MCHECK_MAX
    except (ValueError, AssertionError):
        return await cb.answer()
    coin = settings.coin()
    me = await cb.bot.me()
    lc, lu = lang_of(creator), lang_of(cb.from_user.id, cb.from_user)

    async def set_kb(mk):
        try:
            if cb.inline_message_id:
                await cb.bot.edit_message_reply_markup(inline_message_id=cb.inline_message_id, reply_markup=mk)
            else:
                await cb.message.edit_reply_markup(reply_markup=mk)
        except Exception:
            pass

    if cb.from_user.id == creator:
        st, back = db.mcheck_cancel(cid, creator, amount, total)
        if st == "ok":
            await cb.answer(L(lu, f"Мультичек отменён, {back:g} {coin} вернулись на баланс", f"Multi-check cancelled, {back:g} {coin} returned"), show_alert=True)
            await set_kb(_done_kb(L(lc, "🚫 Мультичек отменён", "🚫 Multi-check cancelled"), me.username))
        else:
            await cb.answer(L(lu, "Мультичек уже недействителен", "This multi-check is no longer valid"), show_alert=True)
        return
    u, _ = db.get_or_create(cb.from_user.id, cb.from_user.first_name, username=cb.from_user.username)
    if u.get("banned"):
        return await cb.answer(L(lu, "Аккаунт заблокирован", "Account blocked"), show_alert=True)
    st, n = db.mcheck_claim(cid, creator, amount, total, cb.from_user.id)
    if st == "ok":
        await cb.answer(L(lu, f"+{amount:g} {coin} на баланс!", f"+{amount:g} {coin} added to your balance!"), show_alert=True)
        await set_kb(_done_kb(L(lc, f"✅ Все {total} активаций получены", f"✅ All {total} claimed"), me.username) if n >= total
                     else _mcheck_kb(cid, creator, amount, total, n, lc))
        try:
            await cb.bot.send_message(cb.from_user.id, L(lu, f"💎 Вы получили <b>{amount:g} {coin}</b> из мультичека!",
                                                         f"💎 You received <b>{amount:g} {coin}</b> from a multi-check!"), reply_markup=kb(lu))
        except Exception:
            pass
        if n >= total:
            try:
                await cb.bot.send_message(creator, L(lc, f"✅ Ваш мультичек {amount:g} {coin} × {total} полностью получен.",
                                                     f"✅ Your multi-check {amount:g} {coin} × {total} has been fully claimed."))
            except Exception:
                pass
    else:
        msgs = {"already": ("Вы уже получили этот мультичек", "You’ve already claimed this multi-check"),
                "done": ("Все активации уже получены", "All activations have been claimed"),
                "cancelled": ("Мультичек отменён отправителем", "Multi-check cancelled by sender"),
                "failed": ("Мультичек недействителен", "Multi-check is invalid"),
                "no_funds": ("У отправителя недостаточно средств", "Sender has insufficient funds")}
        ru_m, en_m = msgs.get(st, msgs["failed"])
        await cb.answer(L(lu, ru_m, en_m), show_alert=True)
