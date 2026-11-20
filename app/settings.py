from . import db
from .config import COIN, DEFAULT_WELCOME, MIN_WITHDRAW


def coin() -> str:
    return db.get_setting("coin_name", COIN)


def welcome() -> str:
    return db.get_setting("welcome_text", DEFAULT_WELCOME).replace("{coin}", coin())


def min_withdraw() -> float:
    return float(db.get_setting("min_withdraw", MIN_WITHDRAW))


def withdraw_enabled() -> bool:
    return db.get_setting("withdraw_enabled", "1") == "1"


def support() -> str:
    return db.get_setting("support_username", "")


def all_settings() -> dict:
    return {
        "coin_name": coin(),
        "welcome_text": db.get_setting("welcome_text", DEFAULT_WELCOME),
        "min_withdraw": min_withdraw(),
        "withdraw_enabled": withdraw_enabled(),
        "support_username": support(),
    }
