"""
Background cleanup worker for temporary files.
"""
import os
import time
import asyncio
import logging

from bot.config import DOWNLOAD_DIR, CLEANUP_MAX_AGE_SECONDS, CLEANUP_INTERVAL_SECONDS
from bot.utils.helpers import safe_remove

logger = logging.getLogger(__name__)


def cleanup_download_dir_once():
    """Remove files older than CLEANUP_MAX_AGE_SECONDS from downloads dir."""
    try:
        now = time.time()
        removed = 0
        for name in os.listdir(DOWNLOAD_DIR):
            path = os.path.join(DOWNLOAD_DIR, name)
            if not os.path.isfile(path):
                continue
            try:
                if now - os.path.getmtime(path) > CLEANUP_MAX_AGE_SECONDS:
                    safe_remove(path)
                    removed += 1
            except Exception:
                pass
        if removed > 0:
            logger.info(f"Cleanup: removed {removed} old files")
    except Exception as e:
        logger.error(f"Cleanup error: {e}")


async def cleanup_worker():
    """Background task that periodically cleans old files."""
    logger.info("Cleanup worker started")
    while True:
        cleanup_download_dir_once()
        await asyncio.sleep(CLEANUP_INTERVAL_SECONDS)
