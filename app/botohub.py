"""Задания-спонсоры от BotoHub (https://botohub.me) во вкладке Missions.

Используется API-токен BotoHub из .env (BOTOHUB_TOKEN), а не токен нашего бота. В BotoHub уходит только
Telegram ID игрока (chat_id) — пол и возраст не передаём. За каждого спонсора награда выдаётся один раз.
"""
import logging
import os
import re

import aiohttp

from . import db

log = logging.getLogger("toncry.botohub")
API = "https://botohub.me/get-tasks-extended"
TOKEN = os.getenv("BOTOHUB_TOKEN", "").strip()


def enabled() -> bool:
    return bool(TOKEN) and db.get_setting("botohub_enabled", "1") == "1"


def reward() -> float:
    return max(0.0, float(db.get_setting("botohub_reward", 0.1)))


async def tasks(user_id: int) -> list[dict]:
    """[{url, resource_id, completed}] — спонсоры для игрока. При ошибке сервиса — пустой список."""
    if not enabled():
        return []
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=8)) as s:
            async with s.post(API, headers={"Auth": TOKEN, "Content-Type": "application/json"},
                              json={"chat_id": user_id, "only_has_check": True}) as r:
                data = await r.json(content_type=None)
    except Exception as e:
        log.warning("BotoHub request failed: %s", e)
        return []
    out = []
    for t in data.get("tasks") or []:
        if isinstance(t, dict) and t.get("url") and t.get("resource_id"):
            out.append({"url": str(t["url"]), "resource_id": str(t["resource_id"]), "completed": bool(t.get("completed"))})
    return out


def title(url: str) -> str:
    m = re.search(r"(?:t|telegram)\.me/(?:\+|joinchat/)?([\w\-]+)", url)
    if m and not re.search(r"(?:t|telegram)\.me/(?:\+|joinchat/)", url):
        return f"Subscribe to @{m.group(1)}"
    return "Join a sponsor channel"
