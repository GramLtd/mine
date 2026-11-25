import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.types import BotCommand

import db
from bot import poller, router
from config import BOT_TOKEN


async def main():
    logging.basicConfig(level=logging.INFO)
    db.init()
    bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
    await bot.set_my_commands([
        BotCommand(command="start", description="Меню"),
        BotCommand(command="add", description="Добавить кошелёк: /add адрес метка"),
        BotCommand(command="remove", description="Удалить кошелёк: /remove адрес"),
        BotCommand(command="channel", description="Канал: /channel @name"),
        BotCommand(command="autopost", description="Автопубликация: /autopost on|off"),
        BotCommand(command="id", description="Мой ID"),
    ])
    dp = Dispatcher()
    dp.include_router(router)
    asyncio.create_task(poller(bot))
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
