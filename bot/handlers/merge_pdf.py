"""
PDF merge handler with media group support.
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
from bot.keyboards import kb_cancel
from bot.states import get_state, STATE_WAIT_PDF_MERGE
from bot.utils.pdf import merge_pdfs
from bot.utils.helpers import safe_remove, user_pdf_filename
from bot.handlers.menu import enforce_subscription, show_main_menu

logger = logging.getLogger(__name__)
router = Router(name="merge_pdf")

# PDF merge buffers
PDF_BUFFER: Dict[Tuple[int, str], List[str]] = {}
PDF_TASK: Dict[Tuple[int, str], asyncio.Task] = {}


@router.message(lambda msg: msg.document and get_state(msg.from_user.id) == STATE_WAIT_PDF_MERGE)
async def handle_merge_pdf(message: Message, bot: Bot):
    """Handle document for PDF merging."""
    user = message.from_user
    user_id = user.id
    upsert_user(user_id, user.username, user.first_name, user.last_name)

    if not await enforce_subscription(bot, user_id):
        return

    doc = message.document
    file_name = (doc.file_name or "").lower()

    # Validate PDF
    if doc.mime_type != "application/pdf" and not file_name.endswith(".pdf"):
        await message.answer("❌ Faqat PDF fayl yuboring.", reply_markup=kb_cancel())
        return

    # File size check
    if doc.file_size and doc.file_size > MAX_FILE_SIZE:
        await message.answer(f"❌ Fayl hajmi juda katta (max {MAX_FILE_SIZE // (1024*1024)}MB).")
        return

    file_path = os.path.join(DOWNLOAD_DIR, f"{user_id}_{doc.file_id}.pdf")
    file = await bot.get_file(doc.file_id)
    await bot.download_file(file.file_path, file_path)

    # Buffer PDFs
    group_id = message.media_group_id or "pdfmerge"
    key = (user_id, str(group_id))
    PDF_BUFFER.setdefault(key, []).append(file_path)
    old_task = PDF_TASK.get(key)
    if old_task and not old_task.done():
        old_task.cancel()

    async def finalize_pdf_group():
        await asyncio.sleep(1.5)
        paths = PDF_BUFFER.pop(key, [])
        PDF_TASK.pop(key, None)
        if not paths:
            return
        if len(paths) < 2:
            for p in paths:
                safe_remove(p)
            await bot.send_message(user_id, "❌ Kamida 2 ta PDF yuboring.",
                                   reply_markup=kb_cancel())
            return

        status = await bot.send_message(user_id, "⏳ PDFlar birlashtirilmoqda...")
        out_pdf = os.path.join(DOWNLOAD_DIR, f"merged_{user_id}_{int(time.time())}.pdf")
        try:
            merge_pdfs(paths, out_pdf)
            result = FSInputFile(out_pdf, filename=user_pdf_filename(user))
            await bot.send_document(user_id, result, caption="✅ PDFlar birlashtirildi!")
            inc_uses_and_log(user_id, "pdf_merge")
            logger.info(f"User {user_id}: pdf_merge ({len(paths)} files)")
        except Exception as e:
            logger.error(f"PDF merge error for user {user_id}: {e}")
            await bot.send_message(user_id, "❌ PDFlarni birlashtirishda xatolik yuz berdi.")
        finally:
            for p in paths:
                safe_remove(p)
            safe_remove(out_pdf)
            try:
                await status.delete()
            except Exception:
                pass
        await show_main_menu(bot, user_id)

    PDF_TASK[key] = asyncio.create_task(finalize_pdf_group())
