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


def max_op() -> int:
    """Сколько спонсоров запрашивать (как в официальном примере BotoHub — max_op: 3)."""
    return max(1, min(10, int(float(db.get_setting("botohub_max_op", 3)))))


def reward() -> float:
    return max(0.0, float(db.get_setting("botohub_reward", 0.1)))


async def tasks(user_id: int) -> list[dict]:
    """[{url, resource_id, completed}] — спонсоры для игрока. При ошибке сервиса — пустой список."""
    if not enabled():
        return []
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=8)) as s:
            async with s.post(API, headers={"Auth": TOKEN, "Content-Type": "application/json"},
                              json={"chat_id": user_id, "max_op": max_op(), "only_has_check": True}) as r:
                data = await r.json(content_type=None)
    except Exception as e:
        log.warning("BotoHub request failed: %s", e)
        return []
    out = []
    for t in data.get("tasks") or []:
        if isinstance(t, dict) and t.get("url") and t.get("resource_id"):
            out.append({"url": str(t["url"]), "resource_id": str(t["resource_id"]), "completed": bool(t.get("completed"))})
    return out


async def diagnose(user_id: int) -> dict:
    """Для админки: что именно отвечает BotoHub (без токена в ответе)."""
    if not TOKEN:
        return {"ok": False, "problem": "BOTOHUB_TOKEN не задан в /opt/hashfan/.env (или бот не перезапущен после добавления)"}
    out = {"enabled_in_admin": db.get_setting("botohub_enabled", "1") == "1", "token_length": len(TOKEN)}
    variants = {"как в боте (max_op, только с проверкой)": {"max_op": max_op(), "only_has_check": True},
                "max_op без фильтра": {"max_op": max_op()},
                "без max_op": {"only_has_check": False}}
    for name, extra in variants.items():
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as s:
                async with s.post(API, headers={"Auth": TOKEN, "Content-Type": "application/json"},
                                  json={"chat_id": user_id, **extra}) as r:
                    body = await r.text()
                    out[name] = {"http": r.status, "body": body[:600]}
        except Exception as e:
            out[name] = {"error": f"{type(e).__name__}: {e}"}
    return out


def title(url: str, resource_id: str = "") -> str:
    """Спонсор-канал → «Subscribe to @…»; спонсор-бот (числовой ID без -100) → «Start @…»."""
    private = re.search(r"(?:t|telegram)\.me/(?:\+|joinchat/)", url)
    m = re.search(r"(?:t|telegram)\.me/([\w\-]+)", url)
    is_bot = resource_id.isdigit() or bool(re.search(r"bot(\?|$)", url, re.I))
    if m and not private:
        return f"{'Start' if is_bot else 'Subscribe to'} @{m.group(1)}"
    return "Start a sponsor bot" if is_bot else "Join a sponsor channel"
