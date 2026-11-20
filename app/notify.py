import asyncio
import logging
import time

from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter

from . import db, game, settings
from .bot import kb
from .config import STORAGE_HOURS

log = logging.getLogger("toncry.notify")


async def storage_watcher(bot, interval: int = 60):
    """Когда хранилище заполнилось и майнинг встал — один раз пишем игроку, сколько он намайнил."""
    while True:
        try:
            for u in db.storage_full_users(time.time(), STORAGE_HOURS):
                db.update(u["id"], full_notified=u["last_claim"])  # отмечаем заранее: не шлём дважды
                amount = game.pending(u)
                hours = game.storage_hours(u)
                text = (f"⛏ <b>Майнинг завершён!</b>\n\n"
                        f"За {hours:g} ч ферма намайнила <b>{amount:.6f} {settings.coin()}</b>.\n"
                        f"Хранилище заполнено — майнинг остановлен. "
                        f"Зайдите в бота и заберите награду, чтобы ферма снова заработала.")
                try:
                    await bot.send_message(u["id"], text, reply_markup=kb())
                except TelegramRetryAfter as e:
                    await asyncio.sleep(e.retry_after)
                except TelegramForbiddenError:
                    pass  # бот заблокирован игроком
                except Exception as e:
                    log.warning("notify %s failed: %s", u["id"], e)
                await asyncio.sleep(0.05)
        except Exception:
            log.exception("storage watcher failed")
        await asyncio.sleep(interval)
