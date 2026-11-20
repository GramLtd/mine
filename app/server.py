import time
from pathlib import Path
from fastapi import FastAPI, Depends, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import db, game
from .auth import current_user
from .config import LEVELS, DAILY_BONUS, CHANNEL_USERNAME, REF_BONUS_COINS

WEB = Path(__file__).resolve().parent.parent / "webapp"
api = FastAPI()
bot = None  # выставляется из main.py


def load(tg):
    name = tg.get("first_name", "") or tg.get("username", "")
    user, _ = db.get_or_create(tg["id"], name)
    return user


@api.get("/api/state")
def get_state(tg=Depends(current_user)):
    return game.state(load(tg))


@api.post("/api/claim")
def claim(tg=Depends(current_user)):
    user = load(tg)
    now = time.time()
    amount = game.pending(user, now)
    db.update(user["id"], balance=user["balance"] + amount, last_claim=now)
    return {"claimed": amount, **game.state(load(tg))}


@api.post("/api/upgrade")
def upgrade(tg=Depends(current_user)):
    user = load(tg)
    if user["level"] + 1 >= len(LEVELS):
        raise HTTPException(400, "Максимальный уровень")
    price = LEVELS[user["level"] + 1][1]
    if user["balance"] < price:
        raise HTTPException(400, "Недостаточно монет")
    # сначала начисляем накопленное по старой скорости
    now = time.time()
    acc = game.pending(user, now)
    db.update(user["id"], balance=user["balance"] - price + acc,
              level=user["level"] + 1, last_claim=now)
    return game.state(load(tg))


@api.get("/api/friends")
def friends(tg=Depends(current_user)):
    user = load(tg)
    uname = getattr(api.state, "bot_username", "your_bot")
    return {"friends": db.friends(user["id"]), "bonus_per_friend": REF_BONUS_COINS,
            "link": f"https://t.me/{uname}?start=ref{user['id']}"}


@api.get("/api/missions")
def missions(tg=Depends(current_user)):
    user = load(tg)
    return {"missions": [
        {"id": "daily", "title": "Ежедневный бонус", "reward": DAILY_BONUS,
         "done": time.time() - user["last_daily"] < 86400},
        *([{"id": "channel", "title": f"Подпишись на {CHANNEL_USERNAME}",
            "reward": DAILY_BONUS * 5, "done": bool(user["channel_done"]),
            "url": f"https://t.me/{CHANNEL_USERNAME.lstrip('@')}"}] if CHANNEL_USERNAME else []),
    ]}


@api.post("/api/missions/{mid}")
async def do_mission(mid: str, tg=Depends(current_user)):
    user = load(tg)
    if mid == "daily":
        if time.time() - user["last_daily"] < 86400:
            raise HTTPException(400, "Уже получено сегодня")
        db.update(user["id"], last_daily=time.time())
        db.add_balance(user["id"], DAILY_BONUS)
    elif mid == "channel" and CHANNEL_USERNAME:
        if user["channel_done"]:
            raise HTTPException(400, "Уже выполнено")
        member = await bot.get_chat_member(CHANNEL_USERNAME, user["id"])
        if member.status in ("left", "kicked"):
            raise HTTPException(400, "Вы не подписаны")
        db.update(user["id"], channel_done=1)
        db.add_balance(user["id"], DAILY_BONUS * 5)
    else:
        raise HTTPException(404)
    return {"ok": True}


@api.get("/")
def index():
    return FileResponse(WEB / "index.html")


api.mount("/static", StaticFiles(directory=WEB), name="static")
