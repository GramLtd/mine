import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
WEBAPP_URL = os.getenv("WEBAPP_URL", "http://localhost:8000")
CHANNEL_USERNAME = os.getenv("CHANNEL_USERNAME", "")
PORT = int(os.getenv("PORT", "8000"))
DB_PATH = os.getenv("DB_PATH", "game.db")

# Админы: по username (без @) и/или по числовому ID. ID надёжнее — username можно сменить.
ADMIN_USERNAMES = {u.strip().lstrip("@").lower() for u in
                   os.getenv("ADMIN_USERNAMES", "ibuybalenciaga").split(",") if u.strip()}
# --- Оплата в TON ---
TON_WALLET = os.getenv("TON_WALLET", "").strip()           # кошелёк, на который приходят оплаты
TONCENTER_API_KEY = os.getenv("TONCENTER_API_KEY", "")     # необязательно, снимает лимит 1 rps
TONCENTER_URL = os.getenv("TONCENTER_URL", "https://toncenter.com/api/v2")
# Цена в TON = звёзды × STAR_RUB / курс TON в рублях (курс берётся с tonapi.io, запасной — в админке)
STAR_RUB = 1.5
TON_RUB_FALLBACK = 250.0
TON_ORDER_TTL = 3600  # сколько секунд ждём оплату по заказу

ADMIN_IDS = {int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip().isdigit()}

# --- Экономика игры (виртуальная валюта, без реальных денег) ---
COIN = "HASH"               # значение по умолчанию; меняется в админке
BASE_HASHRATE = 50          # GH/s на старте
COIN_PER_GH_PER_SEC = 1e-8  # доход: монет в секунду за 1 GH/s
STORAGE_HOURS = 4           # сколько часов копится без "Забрать"
REF_BONUS_COINS = 0.5       # бонус пригласившему, когда друг арендует первый сервер (меняется в админке)
DAILY_BONUS = 0.01
MIN_WITHDRAW = 15           # по умолчанию; меняется в админке
DEFAULT_WELCOME = (
    "<b>Добро пожаловать!</b>\n\n"
    "Ферма майнит, пока вы отдыхаете. Забирайте {coin}, улучшайте уровень, зовите друзей."
)

# Тарифы серверов (аренда на RENT_DAYS дней):
# (ядра CPU, RAM GB, цена аренды в TON, окупаемость в днях, серверов на складе в сутки)
# Чем дороже сервер, тем быстрее окупается (в среднем ~неделя). Хешрейт считается из цены и окупаемости.
SERVERS = [
    (1, 1, 4, 10, 200), (1, 2, 5.5, 9.5, 150), (2, 4, 10, 9, 120), (4, 6, 16, 8, 100), (6, 8, 22, 7.5, 80),
    (6, 12, 30, 7, 60), (8, 16, 40, 6, 40), (12, 22, 55, 5.5, 25), (16, 32, 75, 5, 15), (32, 64, 140, 4, 5),
]
RENT_DAYS = 30
FIRST_DISCOUNT = 0.25    # скидка на первый сервер
UPGRADE_MARKUP = 1.3     # улучшение = разница цен тарифов × 1.3
MINING_FEE = 0.15        # комиссия сервиса с майнинга
NOFEE_PRICE = 100.0      # отключить комиссию навсегда, TON
STOCK_RESET_HOUR_MSK = 12
TOPUP_MIN = 0.1          # минимальное пополнение баланса, TON

# Магазин за Telegram Stars (XTR). id: (название, описание, цена в звёздах, раздел)
SHOP = {
    "skin_gold":    ("Золото", "Скин вентилятора", 150, "skin"),
    "skin_emerald": ("Изумруд", "Скин вентилятора", 150, "skin"),
    "skin_crimson": ("Рубин", "Скин вентилятора", 150, "skin"),
    "skin_ice":     ("Лёд", "Скин вентилятора", 150, "skin"),
    "skin_black":   ("Карбон", "Скин вентилятора", 300, "skin"),
}
STORAGE_ITEMS = {"storage12": 12, "storage24": 24}
