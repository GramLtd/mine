"""Защита бота: анти-флуд для апдейтов Telegram и скрытие секретов в журналах."""
import logging
import os
import time

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery


class AntiFlood(BaseMiddleware):
    """Если пользователь присылает больше `limit` событий за `per` секунд — бот временно его игнорирует."""

    def __init__(self, limit: int = 25, per: float = 10.0, cooldown: float = 30.0):
        self.limit, self.per, self.cooldown = limit, per, cooldown
        self.hits: dict = {}
        self.muted: dict = {}

    async def __call__(self, handler, event, data):
        user = getattr(event, "from_user", None)
        if user is None:
            return await handler(event, data)
        now = time.time()
        if self.muted.get(user.id, 0) > now:
            if isinstance(event, CallbackQuery):
                try:
                    await event.answer("Too many actions — please wait a bit.")
                except Exception:
                    pass
            return None
        q = [t for t in self.hits.get(user.id, ()) if t > now - self.per]
        q.append(now)
        self.hits[user.id] = q
        if len(q) > self.limit:
            self.muted[user.id] = now + self.cooldown
            logging.getLogger("toncry.security").warning("flood: user %s muted for %ss", user.id, self.cooldown)
            return None
        if len(self.hits) > 50000:
            self.hits.clear()
        return await handler(event, data)


class RedactSecrets(logging.Filter):
    """Токены (бота, BotoHub, toncenter) никогда не попадают в журнал — даже внутри текста ошибки."""

    def __init__(self):
        super().__init__()
        self.secrets = [v for v in (os.getenv("BOT_TOKEN"), os.getenv("BOTOHUB_TOKEN"), os.getenv("TONCENTER_API_KEY")) if v and len(v) > 8]

    def filter(self, record):
        if self.secrets:
            msg = record.getMessage()
            for s in self.secrets:
                msg = msg.replace(s, "***")
            record.msg, record.args = msg, ()
        return True


def setup_logging():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    f = RedactSecrets()
    for h in logging.getLogger().handlers:
        h.addFilter(f)
