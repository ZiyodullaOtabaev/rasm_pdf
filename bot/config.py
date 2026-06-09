"""
Application configuration loaded from environment variables.
"""
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# .env faylni loyiha root papkasidan yuklash
# 1) bot/config.py -> parent.parent = loyiha root
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_ENV_FILE = _PROJECT_ROOT / ".env"

# 2) Agar topilmasa, CWD dan izlaymiz
if not _ENV_FILE.exists():
    _ENV_FILE = Path.cwd() / ".env"

# 3) Yuklash
if _ENV_FILE.exists():
    load_dotenv(_ENV_FILE, override=True)
else:
    # Hech bo'lmasa default load_dotenv()
    load_dotenv()

# Bot
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip().strip('"').strip("'")
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN not set in .env")

# Channel
CHANNEL_USER = os.getenv("CHANNEL_USER", "@xonziyy").strip()

# Limits
FREE_USES_BEFORE_SUB = int(os.getenv("FREE_USES_BEFORE_SUB", "15").strip() or "15")
MAX_FILE_SIZE = int(os.getenv("MAX_FILE_SIZE", str(20 * 1024 * 1024)))  # 20MB default

# AI Upscale
REAL_ESRGAN_BIN = os.getenv("REAL_ESRGAN_BIN", "").strip()
REAL_ESRGAN_MODELS = os.getenv("REAL_ESRGAN_MODELS", "").strip()
ENABLE_REAL_AI = os.getenv("ENABLE_REAL_AI", "1").strip() != "0"

# Admin
ADMIN_IDS_RAW = os.getenv("ADMIN_IDS", "").strip()
ADMIN_ID_SINGLE = int(os.getenv("ADMIN_ID", "0") or "0")


def parse_admin_ids(value: str) -> set:
    out = set()
    if value:
        for x in value.split(","):
            x = x.strip()
            if x.isdigit():
                out.add(int(x))
    if ADMIN_ID_SINGLE:
        out.add(ADMIN_ID_SINGLE)
    return out


ADMIN_IDS = parse_admin_ids(ADMIN_IDS_RAW)

# Database
DB_PATH = os.getenv("DB_PATH", "bot.db").strip() or "bot.db"

# Downloads
DOWNLOAD_DIR = os.getenv("DOWNLOAD_DIR", "downloads").strip() or "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# Cleanup
CLEANUP_MAX_AGE_SECONDS = int(os.getenv("CLEANUP_MAX_AGE_SECONDS", str(24 * 3600)))
CLEANUP_INTERVAL_SECONDS = int(os.getenv("CLEANUP_INTERVAL_SECONDS", str(60 * 60)))

# Broadcast
BROADCAST_RATE = int(os.getenv("BROADCAST_RATE", "25"))
