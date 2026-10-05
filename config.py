import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env file if present
BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()

# Comma-separated user IDs of superadmins (e.g. "12345678,98765432")
_superadmin_raw = os.getenv("SUPERADMIN_IDS", "").strip()
SUPERADMIN_IDS = set()
if _superadmin_raw:
    for item in _superadmin_raw.split(","):
        item = item.strip()
        if item.isdigit():
            SUPERADMIN_IDS.add(int(item))

DB_PATH = os.getenv("DB_PATH", str(BASE_DIR / "bot.db"))
