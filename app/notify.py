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
                if amount <= 0:
                    continue
                period = "сутки" if hours == 24 else f"{hours:g} ч"
                text = (f"⛏ <b>Майнинг остановлен</b>\n\n"
                        f"За {period} ваши серверы намайнили <b>{amount:.6f} {settings.coin()}</b>.\n\n"
                        f"Хранилище заполнено. <b>Зайдите и нажмите «Забрать», чтобы майнинг продолжился</b> — "
                        f"пока награда не собрана, серверы не майнят.")
                try:
                    await bot.send_message(u["id"], text, reply_markup=kb())
                except TelegramRetryAfter as e:
                    await asyncio.sleep(e.retry_after)
                except TelegramForbiddenError:
                    pass  # бот заблокирован игроком
                except Exception as e:
                    log.warning("notify %s failed: %s", u["id"], e)
                await asyncio.sleep(0.05)
            for r in db.ref_unpaid():
                if not db.ref_mark_paid(r["id"]):
                    continue
                bonus = settings.ref_bonus()
                db.add_balance(r["referrer"], bonus)
                try:
                    await bot.send_message(r["referrer"], f"🎉 Ваш друг {r['name'] or ''} арендовал сервер — "
                                           f"<b>+{bonus:g} {settings.coin()}</b> на баланс!", reply_markup=kb())
                except Exception:
                    pass
                await asyncio.sleep(0.05)
            for sv in db.servers_expired_unnotified(time.time()):
                db.server_update(sv["id"], expiry_notified=1)
                spec = game.tier_info(sv["tier"])["spec"]
                try:
                    await bot.send_message(sv["user_id"], f"⏳ <b>Аренда сервера закончилась</b>\n\n{spec} больше не майнит. "
                                           f"Продлите его во вкладке «Мои серверы».", reply_markup=kb())
                except TelegramRetryAfter as e:
                    await asyncio.sleep(e.retry_after)
                except Exception:
                    pass
                await asyncio.sleep(0.05)
        except Exception:
            log.exception("storage watcher failed")
        await asyncio.sleep(interval)
