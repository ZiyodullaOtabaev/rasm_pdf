"""
/start command handler.
"""
import logging

from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message

from bot.database import upsert_user
from bot.keyboards import kb_main
from bot.states import set_state, STATE_NONE

logger = logging.getLogger(__name__)
router = Router(name="start")

WELCOME_TEXT = (
    "Assalamu Alaykum! 📌 Rasm yoki matnlaringizni PDF qiling "
    "va rasmlaringizni sifatini oshiring.\n"
    "Quyidan kerakli bo'limni tanlang:"
)


@router.message(CommandStart())
async def cmd_start(message: Message):
    """Handle /start command."""
    user = message.from_user
    upsert_user(user.id, user.username, user.first_name, user.last_name)
    set_state(user.id, STATE_NONE)
    await message.answer(WELCOME_TEXT, reply_markup=kb_main())
    logger.info(f"User {user.id} ({user.username}) started bot")
