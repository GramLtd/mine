import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
WEBAPP_URL = os.getenv("WEBAPP_URL", "http://localhost:8000")
CHANNEL_USERNAME = os.getenv("CHANNEL_USERNAME", "")
PORT = int(os.getenv("PORT", "8000"))
DB_PATH = os.getenv("DB_PATH", "game.db")

# --- Экономика игры (виртуальная валюта, без реальных денег) ---
COIN = "HASH"
BASE_HASHRATE = 50          # GH/s на старте
COIN_PER_GH_PER_SEC = 1e-7  # доход: монет в секунду за 1 GH/s
STORAGE_HOURS = 4           # сколько часов копится без "Забрать"
REF_BONUS_COINS = 0.05      # бонус пригласившему
REF_HASH_BONUS = 0.10       # +10% к хешрейту за каждого друга (макс. ниже)
REF_HASH_BONUS_MAX = 1.0
DAILY_BONUS = 0.01

# Уровни улучшения: (хешрейт GH/s, цена в монетах)
LEVELS = [
    (50, 0), (80, 0.01), (130, 0.03), (210, 0.08), (340, 0.2),
    (550, 0.5), (900, 1.2), (1450, 3.0), (2350, 7.0), (3800, 16.0),
]
