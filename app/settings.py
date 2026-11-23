from . import db
from .config import COIN, DEFAULT_WELCOME, MIN_WITHDRAW, TON_WALLET, STAR_RUB, TON_RUB_FALLBACK


# TON CRY — внутриигровая валюта. Назвать её ровно как реальную криптовалюту нельзя, чтобы не вводить игроков в заблуждение
FORBIDDEN_COIN_NAMES = {"TON", "TONCOIN", "GRAM", "GRAMS", "USDT", "BTC", "ETH", "NOT", "DOGS"}


def coin_name_allowed(name: str) -> bool:
    return name.strip().upper() not in FORBIDDEN_COIN_NAMES


def coin() -> str:
    name = db.get_setting("coin_name", COIN)
    return name if coin_name_allowed(name) else COIN


DEFAULT_WELCOME_EN = ("<b>Welcome!</b>\n\n"
                      "Rent servers — they mine {coin} around the clock. Claim your rewards once a day and invite friends.")


def welcome(lang="ru") -> str:
    if lang == "en":
        return db.get_setting("welcome_text_en", DEFAULT_WELCOME_EN).replace("{coin}", coin())
    return db.get_setting("welcome_text", DEFAULT_WELCOME).replace("{coin}", coin())


DEFAULT_MAINTENANCE = ("We’re doing some maintenance right now. Your servers and balances are safe — "
                       "please check back a little later.")


def maintenance() -> bool:
    """Режим техработ: игроки видят экран «Maintenance», действия для них закрыты (админы работают как обычно)."""
    return db.get_setting("maintenance", "0") == "1"


def maintenance_text() -> str:
    return db.get_setting("maintenance_text", "") or DEFAULT_MAINTENANCE


def reject_templates() -> list:
    import json
    try:
        return json.loads(db.get_setting("reject_templates", "[]"))
    except ValueError:
        return []


def min_withdraw() -> float:
    return float(db.get_setting("min_withdraw", MIN_WITHDRAW))


def withdraw_enabled() -> bool:
    return db.get_setting("withdraw_enabled", "1") == "1"


def support() -> str:
    return db.get_setting("support_username", "")


def ref_bonus() -> float:
    from .config import REF_BONUS_COINS
    return float(db.get_setting("ref_bonus", REF_BONUS_COINS))


def ton_wallet() -> str:
    return db.get_setting("ton_wallet", TON_WALLET) or ""


def star_rub() -> float:
    return float(db.get_setting("star_rub", STAR_RUB))


def ton_rub_fallback() -> float:
    return float(db.get_setting("ton_rub", TON_RUB_FALLBACK))


_rate = {"v": None, "t": 0.0}


def ton_rub() -> float:
    """Курс TON в рублях, кешируется на 10 минут; при ошибке — последний известный или из админки."""
    import json, time, urllib.request
    if time.time() - _rate["t"] < 600 and _rate["v"]:
        return _rate["v"]
    try:
        with urllib.request.urlopen("https://tonapi.io/v2/rates?tokens=ton&currencies=rub", timeout=5) as r:
            v = float(json.load(r)["rates"]["TON"]["prices"]["RUB"])
        if v > 0:
            _rate.update(v=v, t=time.time())
            return v
    except Exception:
        _rate["t"] = time.time() - 540  # повторим через минуту
    return _rate["v"] or ton_rub_fallback()


def stars_to_ton(stars: int) -> float:
    return max(0.01, round(stars * star_rub() / ton_rub(), 2))


def ton_to_stars(amount: float) -> int:
    import math
    return max(1, math.ceil(amount * ton_rub() / star_rub()))


def ton_enabled() -> bool:
    return bool(ton_wallet())


def all_settings() -> dict:
    return {
        "coin_name": coin(),
        "welcome_text": db.get_setting("welcome_text", DEFAULT_WELCOME),
        "welcome_text_en": db.get_setting("welcome_text_en", DEFAULT_WELCOME_EN),
        "min_withdraw": min_withdraw(),
        "withdraw_enabled": withdraw_enabled(),
        "support_username": support(),
        "ton_wallet": ton_wallet(),
        "star_rub": star_rub(),
        "ref_bonus": ref_bonus(),
        "nofee_price": float(db.get_setting("nofee_price", 100)),
        "maintenance": maintenance(),
        "maintenance_text": db.get_setting("maintenance_text", ""),
        "reward_share": float(db.get_setting("reward_share", 0.2)),
        "reward_cap": float(db.get_setting("reward_cap", 10)),
        "accrual_speed": float(db.get_setting("accrual_speed", 1.0)),
        "ton_rub": ton_rub_fallback(),
        "ton_rub_live": ton_rub(),
    }
