import asyncio
import html
import logging
import time

from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter

from . import db, game, settings
from .bot import kb, lang_of
from .i18n import L, t
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
                lg = lang_of(u["id"])
                period = L(lg, "сутки" if hours == 24 else f"{hours:g} ч", "the last 24 hours" if hours == 24 else f"{hours:g} h")
                text = L(lg, f"⛏ <b>Майнинг остановлен</b>\n\n"
                         f"За {period} ваши серверы намайнили <b>{amount:.6f} {settings.coin()}</b>.\n\n"
                         f"Хранилище заполнено. <b>Зайдите и нажмите «Забрать», чтобы майнинг продолжился</b> — "
                         f"пока награда не собрана, серверы не майнят.",
                         f"⛏ <b>Mining stopped</b>\n\n"
                         f"In {period} your servers mined <b>{amount:.6f} {settings.coin()}</b>.\n\n"
                         f"Storage is full. <b>Open the app and tap “Claim” to keep mining</b> — "
                         f"servers don't mine until the reward is collected.")
                try:
                    await bot.send_message(u["id"], text, reply_markup=kb(lg))
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
                    lg = lang_of(r["referrer"])
                    await bot.send_message(r["referrer"], L(lg, f"🎉 Ваш друг {html.escape(r['name'] or '')} арендовал сервер — "
                                           f"<b>+{bonus:g} {settings.coin()}</b> на баланс!",
                                           f"🎉 Your friend {html.escape(r['name'] or '')} rented a server — "
                                           f"<b>+{bonus:g} {settings.coin()}</b> to your balance!"), reply_markup=kb(lg))
                except Exception:
                    pass
                await asyncio.sleep(0.05)
            # автосообщения (напоминания)
            from . import promo
            await promo.tick(bot)
            # итоги недели программы вознаграждений
            from . import rewards
            for uid, amt in rewards.distribute_due():
                lg = lang_of(uid)
                try:
                    await bot.send_message(uid, L(lg, f"🏆 Итоги недели: вознаграждение <b>{amt:g} TON</b> зачислено на ваш баланс вознаграждений.",
                                                  f"🏆 Weekly results: a reward of <b>{amt:g} TON</b> has been added to your rewards balance."),
                                           reply_markup=kb(lg))
                except Exception:
                    pass
                await asyncio.sleep(0.05)
            for sv in db.servers_expired_unnotified(time.time()):
                db.server_update(sv["id"], expiry_notified=1)
                spec = game.tier_info(sv["tier"])["spec"]
                try:
                    lg = lang_of(sv["user_id"])
                    await bot.send_message(sv["user_id"], L(lg, f"⏳ <b>Аренда сервера закончилась</b>\n\n{spec} больше не майнит. "
                                           f"Продлите его во вкладке «Мои серверы».",
                                           f"⏳ <b>Server rental ended</b>\n\n{t(spec, 'en')} has stopped mining. "
                                           f"Renew it in the “Servers” tab."), reply_markup=kb(lg))
                except TelegramRetryAfter as e:
                    await asyncio.sleep(e.retry_after)
                except Exception:
                    pass
                await asyncio.sleep(0.05)
        except Exception:
            log.exception("storage watcher failed")
        await asyncio.sleep(interval)
