import asyncio
import uvicorn
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.types import MenuButtonWebApp, WebAppInfo

from app import db, server, ton
from app.bot import router
from app.config import BOT_TOKEN, PORT, WEBAPP_URL


async def main():
    db.init()
    bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
    server.bot = bot
    me = await bot.get_me()
    server.api.state.bot_username = me.username
    await bot.set_chat_menu_button(menu_button=MenuButtonWebApp(
        text="Играть", web_app=WebAppInfo(url=WEBAPP_URL)))
    dp = Dispatcher()
    dp.include_router(router)
    web = uvicorn.Server(uvicorn.Config(server.api, host="127.0.0.1", port=PORT))
    await asyncio.gather(web.serve(), dp.start_polling(bot), ton.watcher(server.ton_paid))


if __name__ == "__main__":
    asyncio.run(main())
