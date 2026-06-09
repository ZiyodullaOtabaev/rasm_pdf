"""
Common utility functions.
"""
import os
import re
import logging

from aiogram.types import User

logger = logging.getLogger(__name__)


def safe_remove(path: str):
    """Safely remove a file, ignoring errors."""
    try:
        if path and os.path.exists(path):
            os.remove(path)
    except Exception as e:
        logger.warning(f"Failed to remove file {path}: {e}")


def sanitize_filename(s: str) -> str:
    """Sanitize a string to be used as a filename."""
    s = (s or "").strip()
    if not s:
        return ""
    out = []
    for ch in s:
        if ch.isalnum() or ch in ("_", "-", "."):
            out.append(ch)
        else:
            out.append("_")
    base = "".join(out).strip("._-")
    base = re.sub(r"_+", "_", base)
    return base[:40] if base else ""


def user_pdf_filename(user: User) -> str:
    """Generate a PDF filename from user info."""
    base = sanitize_filename(user.username or "") or \
           sanitize_filename(user.first_name or "") or \
           f"user_{user.id}"
    return f"{base}.pdf"
