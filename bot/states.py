"""
User state constants and state management.
"""
from typing import Dict

STATE_NONE = "none"
STATE_WAIT_TEXT = "wait_text"
STATE_WAIT_IMG_PDF = "wait_img_pdf"
STATE_WAIT_UPSCALE = "wait_upscale"
STATE_WAIT_PDF_MERGE = "wait_pdf_merge"
STATE_WAIT_BROADCAST = "wait_broadcast"

# In-memory state storage
USER_STATE: Dict[int, str] = {}


def set_state(user_id: int, state: str):
    """Set user's current state."""
    USER_STATE[user_id] = state


def get_state(user_id: int) -> str:
    """Get user's current state."""
    return USER_STATE.get(user_id, STATE_NONE)
