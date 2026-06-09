"""
Image to PDF handler with media group support.
"""
import os
import time
import asyncio
import logging
from typing import Dict, List, Tuple

from aiogram import Router, Bot
from aiogram.types import Message, FSInputFile

from bot.config import DOWNLOAD_DIR, MAX_FILE_SIZE
from bot.database import upsert_user, inc_uses_and_log
from bot.states import get_state, STATE_WAIT_IMG_PDF
from bot.utils.pdf import images_to_pdf
from bot.utils.helpers import safe_remove, user_pdf_filename
from bot.handlers.menu import enforce_subscription, show_main_menu

logger = logging.getLogger(__name__)
router = Router(name="img_pdf")

# Media group buffers
MEDIA_BUFFER: Dict[Tuple[int, str], List[str]] = {}
MEDIA_TASK: Dict[Tuple[int, str], asyncio.Task] = {}


@router.message(lambda msg: msg.photo and get_state(msg.from_user.id) == STATE_WAIT_IMG_PDF)
async def handle_img_pdf(message: Message, bot: Bot):
    """Handle photo for image-to-PDF conversion."""
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

    # Media group handling
    if message.media_group_id:
        key = (user_id, message.media_group_id)
        MEDIA_BUFFER.setdefault(key, []).append(file_path)
        old_task = MEDIA_TASK.get(key)
        if old_task and not old_task.done():
            old_task.cancel()

        async def finalize_group():
            await asyncio.sleep(1.5)
            paths = MEDIA_BUFFER.pop(key, [])
            MEDIA_TASK.pop(key, None)
            if not paths:
                return
            status = await bot.send_message(user_id, "⏳ PDF tayyorlanmoqda...")
            pdf_path = os.path.join(DOWNLOAD_DIR, f"images_{user_id}_{int(time.time())}.pdf")
            try:
                images_to_pdf(paths, pdf_path)
                doc = FSInputFile(pdf_path, filename=user_pdf_filename(user))
                await bot.send_document(user_id, doc, caption="✅ Tayyor!")
                inc_uses_and_log(user_id, "img_pdf")
                logger.info(f"User {user_id}: img_pdf ({len(paths)} images)")
            except Exception as e:
                logger.error(f"Img PDF group error for user {user_id}: {e}")
                await bot.send_message(user_id, "❌ PDF yaratishda xatolik yuz berdi.")
            finally:
                for p in paths:
                    safe_remove(p)
                safe_remove(pdf_path)
                try:
                    await status.delete()
                except Exception:
                    pass
            await show_main_menu(bot, user_id)

        MEDIA_TASK[key] = asyncio.create_task(finalize_group())
        return

    # Single image
    status = await message.answer("⏳ PDF tayyorlanmoqda...")
    pdf_path = os.path.join(DOWNLOAD_DIR, f"image_{user_id}_{int(time.time())}.pdf")
    try:
        images_to_pdf([file_path], pdf_path)
        doc = FSInputFile(pdf_path, filename=user_pdf_filename(user))
        await bot.send_document(user_id, doc, caption="✅ Tayyor!")
        inc_uses_and_log(user_id, "img_pdf")
        logger.info(f"User {user_id}: img_pdf (1 image)")
    except Exception as e:
        logger.error(f"Img PDF error for user {user_id}: {e}")
        await message.answer("❌ PDF yaratishda xatolik yuz berdi.")
    finally:
        safe_remove(file_path)
        safe_remove(pdf_path)
        try:
            await status.delete()
        except Exception:
            pass
    await show_main_menu(bot, message.chat.id)
