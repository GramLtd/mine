from aiogram import Router, F
from aiogram.filters import CommandStart, CommandObject, Command
from aiogram.types import (Message, InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo,
                           PreCheckoutQuery)

from . import db, game, settings
from .config import WEBAPP_URL, REF_BONUS_COINS, SHOP, ADMIN_IDS, ADMIN_USERNAMES

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
        db.add_balance(user["referrer"], REF_BONUS_COINS)
        try:
            await msg.bot.send_message(
                user["referrer"],
                f"🎉 {msg.from_user.first_name} присоединился по вашей ссылке! +{REF_BONUS_COINS} {settings.coin()}")
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
