"""
Image upscale handler.
"""
import os
import logging

from aiogram import Router, Bot
from aiogram.types import Message, FSInputFile

from bot.config import DOWNLOAD_DIR, MAX_FILE_SIZE
from bot.database import upsert_user, inc_uses_and_log
from bot.states import get_state, STATE_WAIT_UPSCALE
from bot.utils.image import try_realesrgan, pillow_upscale_2x
from bot.utils.helpers import safe_remove
from bot.handlers.menu import enforce_subscription, show_main_menu

logger = logging.getLogger(__name__)
router = Router(name="upscale")


@router.message(lambda msg: msg.photo and get_state(msg.from_user.id) == STATE_WAIT_UPSCALE)
async def handle_upscale(message: Message, bot: Bot):
    """Handle photo for upscaling."""
    user = message.from_user
    user_id = user.id
    upsert_user(user_id, user.username, user.first_name, user.last_name)

    if not await enforce_subscription(bot, user_id):
        return

    photo = message.photo[-1]

    # File size check
    if photo.file_size and photo.file_size > MAX_FILE_SIZE:
        await message.answer(f"❌ Fayl hajmi juda katta (max {MAX_FILE_SIZE // (1024*1024)}MB).")
        return

    file_path = os.path.join(DOWNLOAD_DIR, f"{user_id}_{photo.file_id}.jpg")
    file = await bot.get_file(photo.file_id)
    await bot.download_file(file.file_path, file_path)

    status = await message.answer("⏳ Sifat oshirilmoqda...")
    out_path = os.path.join(DOWNLOAD_DIR, f"{user_id}_{photo.file_id}_up.jpg")
    try:
        ok = try_realesrgan(file_path, out_path)
        if not ok:
            pillow_upscale_2x(file_path, out_path)

        photo_file = FSInputFile(out_path)
        await bot.send_photo(user_id, photo_file, caption="✅ Sifat oshirildi!")
        inc_uses_and_log(user_id, "upscale")
        logger.info(f"User {user_id}: upscale")
    except Exception as e:
        logger.error(f"Upscale error for user {user_id}: {e}")
        await message.answer("❌ Rasm sifatini oshirishda xatolik yuz berdi.")
    finally:
        safe_remove(file_path)
        safe_remove(out_path)
        try:
            await status.delete()
        except Exception:
            pass
    await show_main_menu(bot, message.chat.id)
