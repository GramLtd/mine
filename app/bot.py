from aiogram import Router, F
from aiogram.filters import CommandStart, CommandObject
from aiogram.types import (Message, InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo)

from . import db
from .config import WEBAPP_URL, REF_BONUS_COINS, COIN

router = Router()


def kb():
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="⛏ Открыть майнер", web_app=WebAppInfo(url=WEBAPP_URL))
    ]])


@router.message(CommandStart())
async def start(msg: Message, command: CommandObject):
    ref = None
    if command.args and command.args.startswith("ref"):
        try:
            ref = int(command.args[3:])
        except ValueError:
            pass
    user, created = db.get_or_create(msg.from_user.id, msg.from_user.first_name, ref)
    if created and user["referrer"]:
        db.add_balance(user["referrer"], REF_BONUS_COINS)
        try:
            await msg.bot.send_message(
                user["referrer"],
                f"🎉 {msg.from_user.first_name} присоединился по вашей ссылке! +{REF_BONUS_COINS} {COIN}")
        except Exception:
            pass
    await msg.answer(
        "👋 Добро пожаловать в <b>HashFan</b> — idle-майнер!\n\n"
        "Вентилятор крутится, монеты копятся. Забирай их, улучшай ферму и зови друзей.\n"
        "<i>Это игра: монеты виртуальные.</i>",
        reply_markup=kb())
