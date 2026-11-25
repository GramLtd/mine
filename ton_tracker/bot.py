import asyncio
import base64
import html
import logging

from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton as Btn, InlineKeyboardMarkup, Message

import db
import ton
from config import ADMIN_IDS, POLL_INTERVAL

router = Router()
log = logging.getLogger("tracker")


def is_admin(uid: int) -> bool:
    return uid in ADMIN_IDS


router.message.filter(F.from_user.func(lambda u: is_admin(u.id)) | Command("id", "start"))
router.callback_query.filter(F.from_user.func(lambda u: is_admin(u.id)))


class S(StatesGroup):
    add = State()
    channel = State()
    min_amount = State()


def short(a: str) -> str:
    return f"{a[:6]}…{a[-6:]}"


def menu() -> InlineKeyboardMarkup:
    auto = db.get("autopost", "0") == "1"
    return InlineKeyboardMarkup(inline_keyboard=[
        [Btn(text="➕ Добавить кошелёк", callback_data="add"),
         Btn(text="📋 Кошельки", callback_data="list")],
        [Btn(text=f"📢 Автопубликация: {'ВКЛ ✅' if auto else 'ВЫКЛ ❌'}", callback_data="toggle")],
        [Btn(text="📡 Канал", callback_data="channel"),
         Btn(text="💎 Мин. сумма", callback_data="min")],
    ])


def status_text() -> str:
    ch = db.get("channel") or "не задан"
    return (f"<b>💎 TON трекер переводов</b>\n\n"
            f"Кошельков: <b>{len(db.wallets())}</b>\n"
            f"Канал: <b>{html.escape(ch)}</b>\n"
            f"Автопубликация: <b>{'вкл' if db.get('autopost', '0') == '1' else 'выкл'}</b>\n"
            f"Мин. сумма: <b>{db.get('min_amount', '0')} TON</b>")


# ---------- команды ----------

@router.message(Command("id"))
async def cmd_id(m: Message):
    await m.answer(f"Ваш ID: <code>{m.from_user.id}</code>")


@router.message(Command("start", "menu"))
async def cmd_start(m: Message, state: FSMContext):
    await state.clear()
    if not is_admin(m.from_user.id):
        return await m.answer(f"Нет доступа. Ваш ID: <code>{m.from_user.id}</code> — добавьте его в ADMIN_IDS.")
    await m.answer(status_text(), reply_markup=menu())


async def do_add(m: Message, raw: str):
    parts = raw.split(maxsplit=1)
    if not parts:
        return await m.answer("Формат: <code>адрес [метка]</code>")
    try:
        addr = await ton.normalize(parts[0])
    except Exception as e:
        return await m.answer(f"Ошибка API: {html.escape(str(e))}")
    if not addr:
        return await m.answer("❌ Неверный адрес TON.")
    label = parts[1] if len(parts) > 1 else short(addr)
    try:
        txs, _ = await ton.transactions(addr, limit=1)
        last_lt = int(txs[0]["lt"]) if txs else 0
    except Exception as e:
        return await m.answer(f"Ошибка API: {html.escape(str(e))}")
    db.add_wallet(addr, label, last_lt)
    await m.answer(f"✅ Отслеживаю <b>{html.escape(label)}</b>\n<code>{addr}</code>", reply_markup=menu())


@router.message(Command("add"))
async def cmd_add(m: Message, command: CommandObject):
    await do_add(m, command.args or "")


@router.message(Command("remove"))
async def cmd_remove(m: Message, command: CommandObject):
    addr = (command.args or "").strip()
    try:
        norm = await ton.normalize(addr) if addr else None
    except Exception:
        norm = None
    ok = db.remove_wallet(addr) or (norm and db.remove_wallet(norm))
    await m.answer("🗑 Удалён." if ok else "Не найден.")


@router.message(Command("channel"))
async def cmd_channel(m: Message, command: CommandObject, bot: Bot):
    await set_channel(m, bot, (command.args or "").strip())


@router.message(Command("autopost"))
async def cmd_autopost(m: Message, command: CommandObject):
    on = (command.args or "").strip().lower() in ("on", "1", "вкл")
    db.set("autopost", "1" if on else "0")
    await m.answer(status_text(), reply_markup=menu())


# ---------- кнопки ----------

@router.callback_query(F.data == "add")
async def cb_add(c: CallbackQuery, state: FSMContext):
    await state.set_state(S.add)
    await c.message.answer("Отправьте адрес кошелька и (необязательно) метку через пробел:\n"
                           "<code>UQAbc... Биржа</code>\n\n/start — отмена")
    await c.answer()


@router.message(S.add, F.text)
async def st_add(m: Message, state: FSMContext):
    await state.clear()
    await do_add(m, m.text)


@router.callback_query(F.data == "list")
async def cb_list(c: CallbackQuery):
    ws = db.wallets()
    if not ws:
        await c.answer("Список пуст", show_alert=True)
        return
    text = "<b>📋 Отслеживаемые кошельки:</b>\n\n" + "\n".join(
        f"• <b>{html.escape(w['label'])}</b>\n<code>{w['address']}</code>" for w in ws)
    kb = [[Btn(text=f"🗑 {w['label'][:30]}", callback_data=f"del:{w['address']}")] for w in ws]
    kb.append([Btn(text="⬅️ Назад", callback_data="back")])
    await c.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    await c.answer()


@router.callback_query(F.data.startswith("del:"))
async def cb_del(c: CallbackQuery):
    db.remove_wallet(c.data[4:])
    await c.answer("Удалён")
    if db.wallets():
        await cb_list(c)
    else:
        await c.message.edit_text(status_text(), reply_markup=menu())


@router.callback_query(F.data == "back")
async def cb_back(c: CallbackQuery):
    await c.message.edit_text(status_text(), reply_markup=menu())
    await c.answer()


@router.callback_query(F.data == "toggle")
async def cb_toggle(c: CallbackQuery):
    new = "0" if db.get("autopost", "0") == "1" else "1"
    if new == "1" and not db.get("channel"):
        await c.answer("Сначала укажите канал", show_alert=True)
        return
    db.set("autopost", new)
    await c.message.edit_text(status_text(), reply_markup=menu())
    await c.answer()


@router.callback_query(F.data == "channel")
async def cb_channel(c: CallbackQuery, state: FSMContext):
    await state.set_state(S.channel)
    await c.message.answer("Отправьте @username канала или его ID (-100...).\n"
                           "Бот должен быть администратором канала с правом публикации.")
    await c.answer()


@router.message(S.channel, F.text)
async def st_channel(m: Message, state: FSMContext, bot: Bot):
    await state.clear()
    await set_channel(m, bot, m.text.strip())


async def set_channel(m: Message, bot: Bot, ch: str):
    if not ch:
        return await m.answer("Формат: /channel @username")
    try:
        msg = await bot.send_message(ch, "✅ Бот подключён к каналу.")
        await bot.delete_message(ch, msg.message_id)
    except Exception as e:
        return await m.answer(f"❌ Не могу писать в канал: {html.escape(str(e))}")
    db.set("channel", ch)
    await m.answer("Канал сохранён.\n\n" + status_text(), reply_markup=menu())


@router.callback_query(F.data == "min")
async def cb_min(c: CallbackQuery, state: FSMContext):
    await state.set_state(S.min_amount)
    await c.message.answer("Минимальная сумма перевода для публикации (TON), например <code>1.5</code>:")
    await c.answer()


@router.message(S.min_amount, F.text)
async def st_min(m: Message, state: FSMContext):
    try:
        v = float(m.text.replace(",", "."))
        assert v >= 0
    except Exception:
        return await m.answer("Введите число.")
    await state.clear()
    db.set("min_amount", v)
    await m.answer(status_text(), reply_markup=menu())


# ---------- мониторинг ----------

def fmt(w, t, tx_hash) -> str:
    lines = [
        "💸 <b>Новый перевод TON</b>",
        "",
        f"👛 От: <b>{html.escape(w['label'])}</b>",
        f"<code>{w['address']}</code>",
        f"➡️ Кому: <code>{t['to']}</code>",
        f"💎 Сумма: <b>{t['amount']:,.4f}".rstrip("0").rstrip(".") + " TON</b>",
    ]
    if t["comment"]:
        lines.append(f"💬 Комментарий: {html.escape(t['comment'][:300])}")
    lines.append(f"\n🔗 <a href='https://tonviewer.com/transaction/{tx_hash}'>Tonviewer</a>")
    return "\n".join(lines)


async def notify(bot: Bot, text: str):
    ch = db.get("channel")
    targets = [ch] if db.get("autopost", "0") == "1" and ch else list(ADMIN_IDS)
    for t in targets:
        try:
            await bot.send_message(t, text, disable_web_page_preview=True)
        except Exception as e:
            log.warning("send to %s failed: %s", t, e)


async def check_wallet(bot: Bot, w):
    txs, book = await ton.transactions(w["address"], limit=30)
    new = [tx for tx in txs if int(tx["lt"]) > w["last_lt"]]
    if not new:
        return
    min_amount = float(db.get("min_amount", "0"))
    for tx in reversed(new):  # от старых к новым
        tx_hash = base64.b64decode(tx["hash"]).hex()
        for t in ton.outgoing_transfers(tx, book):
            if t["amount"] >= min_amount:
                await notify(bot, fmt(w, t, tx_hash))
    db.set_lt(w["address"], max(int(tx["lt"]) for tx in new))


async def poller(bot: Bot):
    while True:
        for w in db.wallets():
            try:
                await check_wallet(bot, w)
            except Exception as e:
                log.warning("check %s failed: %s", w["address"], e)
        await asyncio.sleep(POLL_INTERVAL)
