"""
Application configuration loaded from environment variables.
"""
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# .env faylni bir necha joydan izlaymiz
_THIS_FILE = Path(__file__).resolve()
_PROJECT_ROOT = _THIS_FILE.parent.parent  # bot/config.py -> parent=bot/ -> parent=project_root

_possible_env_paths = [
    _PROJECT_ROOT / ".env",
    Path.cwd() / ".env",
    Path(os.path.dirname(os.path.abspath(sys.argv[0] if sys.argv[0] else "."))) / ".env",
]

_env_loaded = False
for _env_path in _possible_env_paths:
    if _env_path.exists():
        load_dotenv(str(_env_path), override=True)
        _env_loaded = True
        print(f"[CONFIG] .env loaded from: {_env_path}")
        break

if not _env_loaded:
    load_dotenv()  # oxirgi harakat: default
    print(f"[CONFIG] WARNING: .env file not found! Searched:")
    for p in _possible_env_paths:
        print(f"  - {p} (exists={p.exists()})")
    print(f"[CONFIG] CWD = {Path.cwd()}")

# Bot
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip().strip('"').strip("'")
if not BOT_TOKEN:
    print("\n[ERROR] BOT_TOKEN is empty!")
    print(f"[DEBUG] All env vars with 'BOT': {[(k,v[:10]+'...') for k,v in os.environ.items() if 'BOT' in k.upper()]}")
    raise RuntimeError(
        "BOT_TOKEN not set in .env\n"
        f"Searched paths: {[str(p) for p in _possible_env_paths]}\n"
        "Please create .env file with: BOT_TOKEN=your_token_here"
    )

# Channel
CHANNEL_USER = os.getenv("CHANNEL_USER", "@xonziyy").strip()

# Limits
FREE_USES_BEFORE_SUB = int(os.getenv("FREE_USES_BEFORE_SUB", "15").strip() or "15")
MAX_FILE_SIZE = int(os.getenv("MAX_FILE_SIZE", str(20 * 1024 * 1024)))

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
