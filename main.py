import asyncio
import os
import uvicorn
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.types import MenuButtonWebApp, WebAppInfo

from app import db, server, ton, notify
from app.bot import router
from app.checks import router as checks_router
from app.config import BOT_TOKEN, PORT, WEBAPP_URL


async def main():
    from app.security import setup_logging, AntiFlood
    setup_logging()  # токены не попадут в журналы
    db.init()
    bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
    server.bot = bot
    me = await bot.get_me()
    server.api.state.bot_username = me.username
    db.set_setting("bot_username", me.username)
    await bot.set_chat_menu_button(menu_button=MenuButtonWebApp(
        text="Play", web_app=WebAppInfo(url=WEBAPP_URL)))
    dp = Dispatcher()
    flood = AntiFlood()  # защита от флуда: слишком частые сообщения/нажатия игнорируются
    for obs in (dp.message, dp.callback_query):  # inline-запросы не трогаем: Telegram шлёт их на каждый символ
        obs.outer_middleware(flood)
    dp.include_router(checks_router)  # раньше основного: ввод суммы чека не должен уходить в поддержку
    dp.include_router(router)
    # IP игроков не пишем в журнал (включить для отладки: ACCESS_LOG=1)
    web = uvicorn.Server(uvicorn.Config(server.api, host="127.0.0.1", port=PORT,
                                        access_log=os.getenv("ACCESS_LOG", "0") == "1"))
    await asyncio.gather(web.serve(), dp.start_polling(bot), ton.watcher(server.ton_paid),
                         notify.storage_watcher(bot))


if __name__ == "__main__":
    asyncio.run(main())
