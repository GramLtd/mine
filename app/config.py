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
ADMIN_IDS = {int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip().isdigit()}

# --- Экономика игры (виртуальная валюта, без реальных денег) ---
COIN = "HASH"               # значение по умолчанию; меняется в админке
BASE_HASHRATE = 50          # GH/s на старте
COIN_PER_GH_PER_SEC = 1e-6  # доход: монет в секунду за 1 GH/s (×10)
STORAGE_HOURS = 4           # сколько часов копится без "Забрать"
REF_BONUS_COINS = 0.05      # бонус пригласившему
REF_HASH_BONUS = 0.10       # +10% к хешрейту за каждого друга (макс. ниже)
REF_HASH_BONUS_MAX = 1.0
DAILY_BONUS = 0.01
MIN_WITHDRAW = 15           # по умолчанию; меняется в админке
DEFAULT_WELCOME = (
    "<b>Добро пожаловать!</b>\n\n"
    "Ферма майнит, пока вы отдыхаете. Забирайте {coin}, улучшайте уровень, зовите друзей."
)

# Уровни улучшения: (хешрейт GH/s, цена в монетах)
LEVELS = [
    (50, 0), (80, 0.01), (130, 0.03), (210, 0.08), (340, 0.2),
    (550, 0.5), (900, 1.2), (1450, 3.0), (2350, 7.0), (3800, 16.0),
]

# Магазин за Telegram Stars (XTR). id: (название, описание, цена в звёздах, раздел)
SHOP = {
    "boost2":    ("Буст ×2 · 24 ч", "Удваивает скорость майнинга на сутки", 500, "boost"),
    "boost3":    ("Буст ×3 · 24 ч", "Утраивает скорость майнинга на сутки", 750, "boost"),
    "level":     ("+1 уровень", "Следующий уровень фермы без оплаты монетами", 100, "boost"),
    "storage12": ("Хранилище 12 ч", "Монеты копятся до 12 часов без захода · навсегда", 250, "storage"),
    "storage24": ("Хранилище 24 ч", "Монеты копятся целые сутки · навсегда", 450, "storage"),
    "skin_gold":    ("Золото", "Скин вентилятора", 150, "skin"),
    "skin_emerald": ("Изумруд", "Скин вентилятора", 150, "skin"),
    "skin_crimson": ("Рубин", "Скин вентилятора", 150, "skin"),
    "skin_ice":     ("Лёд", "Скин вентилятора", 150, "skin"),
    "skin_black":   ("Карбон", "Скин вентилятора", 300, "skin"),
}
STORAGE_ITEMS = {"storage12": 12, "storage24": 24}
