"""Меню чеков в боте (/checks), как в Crypto Bot: создание чека и мультичека, список, карточка чека
(ссылка, «Поделиться», QR-код, описание, обязательная подписка, удаление) и активация по ссылке t.me/бот?start=c_…

Сумма списывается с баланса создателя сразу при создании; при удалении неактивированный остаток возвращается.
Тексты для игроков — на английском.
"""
import html
import io
import re
import secrets

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import (Message, CallbackQuery, InlineQuery, InlineKeyboardMarkup, InlineKeyboardButton,
                           InlineQueryResultPhoto, BufferedInputFile, InlineQueryResultsButton)

from . import db, settings
from .config import WEBAPP_URL, ADMIN_IDS

router = Router()
CHECK_MIN, MAX_ACTIVATIONS = 0.01, 1000
_st: dict = {}  # user_id → {"step": ..., ...} — ввод суммы / количества / описания / канала


def _kb(rows):
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _btn(text, data=None, **kw):
    return InlineKeyboardButton(text=text, callback_data=data, **kw) if data else InlineKeyboardButton(text=text, **kw)


def _num(text):
    m = re.fullmatch(r"\s*(\d+(?:[.,]\d{1,4})?)\s*", text or "")
    return float(m.group(1).replace(",", ".")) if m else None


async def _link(bot, nonce):
    me = await bot.me()
    return f"https://t.me/{me.username}?start=c_{nonce}"


def _menu_kb():
    return _kb([[_btn("🎁 Create check", "ck:new:s"), _btn("👥 Create multi-check", "ck:new:m")],
                [_btn("📋 My checks", "ck:list")]])


async def menu(msg_or_cb, edit=False):
    uid = msg_or_cb.from_user.id
    u = db.get(uid)
    text = (f"🎁 <b>Checks</b>\n\nSend {settings.coin()} to friends: create a check and share the link "
            f"or send it to any chat.\n\nBalance: <b>{(u or {}).get('balance', 0):.4f} {settings.coin()}</b>")
    if edit and isinstance(msg_or_cb, CallbackQuery):
        try:
            return await msg_or_cb.message.edit_text(text, reply_markup=_menu_kb())
        except Exception:
            pass
    target = msg_or_cb.message if isinstance(msg_or_cb, CallbackQuery) else msg_or_cb
    await target.answer(text, reply_markup=_menu_kb())


def _card_text(c, link):
    coin = settings.coin()
    multi = c["total"] > 1
    lines = [f"🎁 <b>{'Multi-check' if multi else 'Check'}</b>", ""]
    lines.append(f"Amount: 💎 <b>{c['amount']:g} {coin}</b>" + (" per activation" if multi else ""))
    if multi:
        lines.append(f"Activations: <b>{c['claimed']}/{c['total']}</b> · total {c['amount'] * c['total']:g} {coin}")
    if c.get("description"):
        lines.append(f"Description: {html.escape(c['description'])}")
    lines.append("")
    if c.get("require_chat"):
        lines.append(f"Only subscribers of <b>{html.escape(c['require_chat'])}</b> can activate this check.")
    else:
        lines.append("<b>Anyone</b> can activate this check.")
    lines += ["", "Copy the link to share the check:", f"<tg-spoiler>{link}</tg-spoiler>", "",
              "⚠️ <b><i>Never send a screenshot of your check or its link to people you don’t trust — "
              "anyone with the link can activate it.</i></b>"]
    return "\n".join(lines)


def _card_kb(c):
    n = c["nonce"]
    return _kb([[_btn("🔗 Share check", switch_inline_query=f"c_{n}")],
                [_btn("Show QR code", f"ck:qr:{n}")],
                [_btn("Edit description" if c.get("description") else "Add description", f"ck:desc:{n}")],
                [_btn("Restrictions", f"ck:lim:{n}")],
                [_btn("Delete check", f"ck:del:{n}")],
                [_btn("‹ Back to list", "ck:list")]])


async def show_card(target, c, bot, edit=False):
    text, kb = _card_text(c, await _link(bot, c["nonce"])), _card_kb(c)
    if edit:
        try:
            return await target.edit_text(text, reply_markup=kb, disable_web_page_preview=True)
        except Exception:
            pass
    await target.answer(text, reply_markup=kb, disable_web_page_preview=True)


def _own(nonce, uid):
    c = db.mcheck_get(nonce)
    return c if c and c["creator"] == uid else None


# ---------- команды и меню ----------
@router.message(Command("checks"))
async def checks_cmd(msg: Message):
    _st.pop(msg.from_user.id, None)
    await menu(msg)


@router.callback_query(F.data.startswith("ck:"))
async def checks_cb(cb: CallbackQuery):
    parts = cb.data.split(":")
    act, arg = parts[1], (parts[2] if len(parts) > 2 else "")
    uid = cb.from_user.id
    u = db.get(uid)
    if not u or u.get("banned"):
        return await cb.answer("Open the app first", show_alert=True)
    if settings.maintenance() and uid not in ADMIN_IDS:
        return await cb.answer("Maintenance — checks are temporarily unavailable.", show_alert=True)
    coin = settings.coin()
    if act == "menu":
        _st.pop(uid, None)
        await cb.answer()
        return await menu(cb, edit=True)
    if act == "new":
        _st[uid] = {"step": "amount", "multi": arg == "m"}
        await cb.answer()
        q = "per activation" if arg == "m" else ""
        return await cb.message.answer(f"Send the amount {q} in {coin}, e.g. <code>1.5</code>.\n"
                                       f"Balance: {u['balance']:.4f} {coin}", reply_markup=_kb([[_btn("Cancel", "ck:menu")]]))
    if act == "list":
        _st.pop(uid, None)
        rows = db.checks_of(uid)
        await cb.answer()
        if not rows:
            return await cb.message.edit_text("You have no active checks.", reply_markup=_menu_kb())
        kb = [[_btn(f"{'👥' if c['total'] > 1 else '🎁'} {c['amount']:g} {coin}" + (f" · {c['claimed']}/{c['total']}" if c['total'] > 1 else "")
                    + (f" · {c['description'][:18]}" if c.get('description') else ""), f"ck:open:{c['nonce']}")] for c in rows]
        kb.append([_btn("‹ Back", "ck:menu")])
        return await cb.message.edit_text("📋 <b>Your active checks</b>", reply_markup=_kb(kb))
    c = _own(arg, uid)
    if not c:
        return await cb.answer("Check not found", show_alert=True)
    if act == "open":
        await cb.answer()
        return await show_card(cb.message, c, cb.bot, edit=True)
    if act == "qr":
        import qrcode
        link = await _link(cb.bot, c["nonce"])
        img = qrcode.make(link, box_size=10, border=2)
        buf = io.BytesIO()
        img.save(buf, "PNG")
        await cb.answer()
        return await cb.message.answer_photo(BufferedInputFile(buf.getvalue(), "check.png"),
                                             caption=f"QR code for the check {c['amount']:g} {coin}")
    if act == "desc":
        _st[uid] = {"step": "desc", "nonce": c["nonce"]}
        await cb.answer()
        return await cb.message.answer("Send a description for the check (up to 100 characters).",
                                       reply_markup=_kb([[_btn("Remove description", f"ck:descoff:{c['nonce']}")], [_btn("Cancel", f"ck:open:{c['nonce']}")]]))
    if act == "descoff":
        _st.pop(uid, None)
        db.check_set(c["nonce"], uid, description="")
        await cb.answer("Description removed")
        return await show_card(cb.message, db.mcheck_get(c["nonce"]), cb.bot)
    if act == "lim":
        await cb.answer()
        cur = c.get("require_chat")
        text = ("🔒 <b>Restrictions</b>\n\n" + (f"Activation requires a subscription to <b>{html.escape(cur)}</b>." if cur else
                "Anyone can activate this check now.") +
                "\n\nTo require a subscription, add this bot as an <b>admin</b> of your channel or group, "
                "then tap the button below and send its @username.")
        rows = [[_btn("Require subscription", f"ck:limset:{c['nonce']}")]]
        if cur:
            rows.append([_btn("Remove restriction", f"ck:limoff:{c['nonce']}")])
        rows.append([_btn("‹ Back to check", f"ck:open:{c['nonce']}")])
        return await cb.message.edit_text(text, reply_markup=_kb(rows))
    if act == "limset":
        _st[uid] = {"step": "chat", "nonce": c["nonce"]}
        await cb.answer()
        return await cb.message.answer("Send the channel or group username, e.g. <code>@mychannel</code>.",
                                       reply_markup=_kb([[_btn("Cancel", f"ck:open:{c['nonce']}")]]))
    if act == "limoff":
        db.check_set(c["nonce"], uid, require_chat="")
        await cb.answer("Restriction removed")
        return await show_card(cb.message, db.mcheck_get(c["nonce"]), cb.bot, edit=True)
    if act == "del":
        await cb.answer()
        left = c["amount"] * (c["total"] - c["claimed"])
        return await cb.message.edit_text(f"Delete this check? {left:g} {coin} will return to your balance.",
                                          reply_markup=_kb([[_btn("Yes, delete", f"ck:delok:{c['nonce']}")],
                                                            [_btn("‹ Back to check", f"ck:open:{c['nonce']}")]]))
    if act == "delok":
        st, back = db.mcheck_cancel(c["nonce"], uid, c["amount"], c["total"])
        await cb.answer(f"Deleted, {back:g} {coin} returned" if st == "ok" else "Already inactive", show_alert=True)
        return await menu(cb, edit=True)


# ---------- ввод текста в шагах меню (раньше общего обработчика поддержки) ----------
@router.message(F.chat.type == "private", F.text, ~F.text.startswith("/"), lambda m: m.from_user.id in _st)
async def checks_input(msg: Message):
    uid, st, coin = msg.from_user.id, _st[msg.from_user.id], settings.coin()
    u = db.get(uid)
    if st["step"] == "amount":
        a = _num(msg.text)
        if a is None or a < CHECK_MIN:
            return await msg.answer(f"Send a number, minimum {CHECK_MIN:g}.")
        if st["multi"]:
            _st[uid] = {"step": "count", "multi": True, "amount": a}
            return await msg.answer(f"How many people can activate it? Send a number from 2 to {MAX_ACTIVATIONS}.",
                                    reply_markup=_kb([[_btn("Cancel", "ck:menu")]]))
        return await _create(msg, a, 1)
    if st["step"] == "count":
        n = int(_num(msg.text) or 0)
        if not 2 <= n <= MAX_ACTIVATIONS:
            return await msg.answer(f"Send a whole number from 2 to {MAX_ACTIVATIONS}.")
        return await _create(msg, st["amount"], n)
    if st["step"] == "desc":
        _st.pop(uid, None)
        db.check_set(st["nonce"], uid, description=msg.text.strip()[:100])
        c = _own(st["nonce"], uid)
        return await show_card(msg, c, msg.bot) if c else None
    if st["step"] == "chat":
        chat = msg.text.strip().replace("https://t.me/", "@").split("?")[0]
        if not chat.startswith("@"):
            chat = "@" + chat
        try:
            me = await msg.bot.me()
            member = await msg.bot.get_chat_member(chat, me.id)
            if member.status not in ("administrator", "creator"):
                raise ValueError
        except Exception:
            return await msg.answer(f"I can’t check subscribers of {html.escape(chat)}. Add this bot as an admin there and try again.")
        _st.pop(uid, None)
        db.check_set(st["nonce"], uid, require_chat=chat)
        c = _own(st["nonce"], uid)
        await msg.answer(f"✅ Now only subscribers of {html.escape(chat)} can activate the check.")
        return await show_card(msg, c, msg.bot) if c else None


async def _create(msg: Message, amount: float, total: int):
    uid, coin = msg.from_user.id, settings.coin()
    _st.pop(uid, None)
    nonce = secrets.token_hex(8)
    if not db.check_create(nonce, uid, round(amount, 4), total):
        u = db.get(uid)
        return await msg.answer(f"Insufficient balance: need {amount * total:g} {coin}, you have {u['balance']:.4f}.",
                                reply_markup=_menu_kb())
    await show_card(msg, db.mcheck_get(nonce), msg.bot)


# ---------- «Поделиться»: @бот c_<id> → карточка чека с кнопкой активации ----------
def claim_kb(c, bot_username):
    coin = settings.coin()
    label = f"💎 Claim {c['amount']:g} {coin}" + (f" · {c['claimed']}/{c['total']}" if c["total"] > 1 else "")
    rows = [[_btn(label, f"k:{c['nonce']}")]]
    if c.get("require_chat"):
        rows.append([_btn(f"Subscribe to {c['require_chat']}", url=f"https://t.me/{c['require_chat'].lstrip('@')}")])
    return _kb(rows)


@router.inline_query(F.query.regexp(r"^c_[0-9a-f]{16}$"))
async def share_inline(q: InlineQuery):
    c = _own(q.query[2:], q.from_user.id)
    if not c or c["status"] != "active":
        return await q.answer([], cache_time=0, is_personal=True,
                              button=InlineQueryResultsButton(text="Check not found — open /checks", start_parameter="checks"))
    coin, me = settings.coin(), await q.bot.me()
    base = WEBAPP_URL.rstrip("/")
    multi = c["total"] > 1
    caption = (f"🎁 {'Multi-check' if multi else 'Check'}: 💎 <b>{c['amount']:g} {coin}</b>"
               + (f" each — for {c['total']} people" if multi else "") + "."
               + (f"\n{html.escape(c['description'])}" if c.get("description") else "")
               + (f"\n\n🔒 Subscribe to {html.escape(c['require_chat'])} to activate." if c.get("require_chat") else ""))
    await q.answer([InlineQueryResultPhoto(
        id=c["nonce"], photo_url=f"{base}/check/{c['amount']:g}.jpg" + (f"?n={c['total']}" if multi else ""),
        thumbnail_url=f"{base}/check/{c['amount']:g}.jpg?thumb=1", photo_width=1280, photo_height=720,
        title=f"{'Multi-check' if multi else 'Check'} {c['amount']:g} {coin}" + (f" × {c['total']}" if multi else ""),
        description=c.get("description") or "Tap to send", caption=caption, parse_mode="HTML",
        reply_markup=claim_kb(c, me.username))], cache_time=0, is_personal=True)


# ---------- активация ----------
async def _subscribed(bot, chat, uid) -> bool:
    try:
        m = await bot.get_chat_member(chat, uid)
        return m.status not in ("left", "kicked")
    except Exception:
        return False


async def activate(bot, user_tg, nonce):
    """Возвращает (ok, текст ответа, чек)."""
    coin = settings.coin()
    c = db.mcheck_get(nonce)
    if not c:
        return False, "Check not found.", None
    if c["status"] != "active":
        return False, {"done": "All activations of this check have been used.", "cancelled": "This check was deleted by its creator."}.get(
            c["status"], "This check is no longer valid."), c
    if user_tg.id == c["creator"]:
        return False, "This is your check — manage it in /checks.", c
    u, _ = db.get_or_create(user_tg.id, user_tg.first_name, username=user_tg.username)
    if u.get("banned"):
        return False, "Your account is blocked.", c
    if settings.maintenance() and user_tg.id not in ADMIN_IDS:
        return False, "Maintenance — checks are temporarily unavailable.", c
    if c.get("require_chat") and not await _subscribed(bot, c["require_chat"], user_tg.id):
        return False, f"Subscribe to {c['require_chat']} to activate this check.", c
    st, n = db.mcheck_claim(nonce, c["creator"], c["amount"], c["total"], user_tg.id)
    if st != "ok":
        return False, {"already": "You’ve already activated this check.", "done": "All activations of this check have been used."}.get(
            st, "This check is no longer valid."), db.mcheck_get(nonce)
    c = db.mcheck_get(nonce)
    try:
        if n >= c["total"]:
            await bot.send_message(c["creator"], f"✅ Your check {c['amount']:g} {coin}" + (f" × {c['total']}" if c["total"] > 1 else "") + " has been fully activated.")
        elif c["total"] == 1:
            pass
    except Exception:
        pass
    return True, f"+{c['amount']:g} {coin} added to your balance!", c


@router.callback_query(F.data.regexp(r"^k:[0-9a-f]{16}$"))
async def claim_cb(cb: CallbackQuery):
    nonce = cb.data[2:]
    ok, text, c = await activate(cb.bot, cb.from_user, nonce)
    await cb.answer(text, show_alert=True)
    if c:
        me = await cb.bot.me()
        done = c["status"] != "active"
        mk = (_kb([[_btn("✅ All activations used" if c["status"] == "done" else "🚫 Check deleted", url=f"https://t.me/{me.username}")]])
              if done else claim_kb(c, me.username))
        try:
            if cb.inline_message_id:
                await cb.bot.edit_message_reply_markup(inline_message_id=cb.inline_message_id, reply_markup=mk)
            elif ok:
                await cb.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass
    if ok:
        try:
            await cb.bot.send_message(cb.from_user.id, f"💎 You activated a check: <b>{text.split(' added')[0]}</b>.")
        except Exception:
            pass


async def start_activate(msg: Message, nonce: str):
    """t.me/бот?start=c_<id> — активация по ссылке (в личке можно показать кнопку подписки)."""
    ok, text, c = await activate(msg.bot, msg.from_user, nonce)
    if ok:
        return await msg.answer(f"💎 {text}")
    if c and c.get("require_chat") and "Subscribe" in text:
        return await msg.answer(f"🔒 {html.escape(text)}", reply_markup=_kb([
            [_btn(f"Subscribe to {c['require_chat']}", url=f"https://t.me/{c['require_chat'].lstrip('@')}")],
            [_btn("I’ve subscribed — activate", f"k:{nonce}")]]))
    await msg.answer(html.escape(text))
