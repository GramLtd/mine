import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.environ["BOT_TOKEN"]
ADMIN_IDS = {int(x) for x in os.getenv("ADMIN_IDS", "").replace(" ", "").split(",") if x}
TONCENTER_API_KEY = os.getenv("TONCENTER_API_KEY", "")
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "20"))
DB_PATH = os.getenv("DB_PATH", "tracker.db")
