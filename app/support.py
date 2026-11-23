"""Поддержка прямо в боте: обращения игроков приходят админам, ответы уходят игроку от имени бота."""
import html

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from . import db
from .config import ADMIN_IDS


def _admin_kb(tid):
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✍️ Ответить", callback_data=f"tk:r:{tid}"),
        InlineKeyboardButton(text="✅ Закрыть", callback_data=f"tk:c:{tid}")]])


async def from_user(bot, user, text: str) -> int:
    """Сообщение игрока → обращение + уведомление админам (ответить можно реплаем на это сообщение)."""
    tid = db.ticket_open_for(user["id"])
    db.ticket_add(tid, text)
    who = html.escape(user.get("name") or "") + (f" @{user['username']}" if user.get("username") else "")
    for aid in ADMIN_IDS:
        try:
            m = await bot.send_message(aid, f"🆘 <b>Обращение #{tid}</b> от {who} (<code>{user['id']}</code>)\n\n{html.escape(text)}\n\n"
                                            f"<i>Ответьте реплаем на это сообщение или кнопкой ниже.</i>", reply_markup=_admin_kb(tid))
            db.ticket_link(aid, m.message_id, tid)
        except Exception:
            pass
    return tid


async def from_admin(bot, tid: int, text: str) -> bool:
    t = db.ticket_get(tid)
    if not t:
        return False
    db.ticket_add(tid, text, from_admin=True)
    try:
        await bot.send_message(t["user_id"], f"💬 <b>Support</b>\n\n{html.escape(text)}\n\n<i>Reply right here or in the app (Support).</i>")
    except Exception:
        return False
    return True


async def close(bot, tid: int):
    t = db.ticket_get(tid)
    if not t:
        return
    db.ticket_close(tid)
    try:
        await bot.send_message(t["user_id"], "✅ Your support request has been closed. Write here anytime if you need help again.")
    except Exception:
        pass
