from . import db
from .config import COIN, DEFAULT_WELCOME, MIN_WITHDRAW, TON_WALLET, TON_PRICES


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


def ton_wallet() -> str:
    return db.get_setting("ton_wallet", TON_WALLET) or ""


def ton_price(item) -> float:
    return float(db.get_setting(f"ton_price_{item}", TON_PRICES.get(item, 0)))


def ton_prices() -> dict:
    """Только товары с ценой > 0 и только если задан кошелёк."""
    if not ton_wallet():
        return {}
    return {k: p for k in TON_PRICES if (p := ton_price(k)) > 0}


def all_settings() -> dict:
    return {
        "coin_name": coin(),
        "welcome_text": db.get_setting("welcome_text", DEFAULT_WELCOME),
        "min_withdraw": min_withdraw(),
        "withdraw_enabled": withdraw_enabled(),
        "support_username": support(),
        "ton_wallet": ton_wallet(),
        "ton_prices": {k: ton_price(k) for k in TON_PRICES},
    }
