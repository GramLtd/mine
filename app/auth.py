import hashlib
import hmac
import json
import time
from urllib.parse import parse_qsl
from fastapi import Header, HTTPException
from .config import BOT_TOKEN


def verify_init_data(init_data: str, max_age: int = 86400) -> dict:
    """Проверка подписи Telegram WebApp initData."""
    data = dict(parse_qsl(init_data, keep_blank_values=True))
    received = data.pop("hash", None)
    if not received:
        raise HTTPException(401, "no hash")
    check = "\n".join(f"{k}={v}" for k, v in sorted(data.items()))
    secret = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
    calc = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(calc, received):
        raise HTTPException(401, "bad signature")
    if time.time() - int(data.get("auth_date", 0)) > max_age:
        raise HTTPException(401, "expired")
    return json.loads(data["user"])


def current_user(x_init_data: str = Header(...)) -> dict:
    return verify_init_data(x_init_data)
