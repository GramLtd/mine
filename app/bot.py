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
        InlineKeyboardButton(text="Открыть HashFan", web_app=WebAppInfo(url=WEBAPP_URL))
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
    item, _, uid = q.invoice_payload.partition(":")
    ok = item in SHOP and uid == str(q.from_user.id) and q.total_amount == SHOP[item][2]
    user = db.get(q.from_user.id)
    if ok and user and not user.get("banned"):
        await q.answer(ok=True)
    else:
        await q.answer(ok=False, error_message="Не удалось оформить покупку, попробуйте ещё раз.")


@router.message(F.successful_payment)
async def paid(msg: Message):
    sp = msg.successful_payment
    item = sp.invoice_payload.partition(":")[0]
    if db.add_payment(sp.telegram_payment_charge_id, msg.from_user.id, item, sp.total_amount):
        game.apply_item(msg.from_user.id, item)
    await msg.answer(f"⭐ Спасибо! «{SHOP.get(item, ('Покупка',))[0]}» активирован.", reply_markup=kb())


@router.message(Command("paysupport"))
async def paysupport(msg: Message):
    await msg.answer("По вопросам оплаты напишите администратору. Возврат Stars возможен по запросу.")
