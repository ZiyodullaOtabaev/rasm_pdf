"""
PDF compression handler.
"""
import os
import logging

from aiogram import Router, Bot
from aiogram.types import Message, FSInputFile

from bot.config import DOWNLOAD_DIR, MAX_FILE_SIZE
from bot.database import upsert_user, inc_uses_and_log
from bot.states import get_state, STATE_WAIT_COMPRESS_PDF
from bot.utils.pdf import compress_pdf
from bot.utils.helpers import safe_remove, user_pdf_filename
from bot.handlers.menu import enforce_subscription, show_main_menu

logger = logging.getLogger(__name__)
router = Router(name="compress")


@router.message(lambda msg: msg.document and get_state(msg.from_user.id) == STATE_WAIT_COMPRESS_PDF)
async def handle_compress_pdf(message: Message, bot: Bot):
    """Handle document for PDF compression."""
    user = message.from_user
    user_id = user.id
    upsert_user(user_id, user.username, user.first_name, user.last_name)

    if not await enforce_subscription(bot, user_id):
        return

    doc = message.document
    file_name = (doc.file_name or "").lower()

    # Validate PDF
    if doc.mime_type != "application/pdf" and not file_name.endswith(".pdf"):
        await message.answer("❌ Faqat PDF fayl yuboring.")
        return

    # File size check
    if doc.file_size and doc.file_size > MAX_FILE_SIZE:
        await message.answer(f"❌ Fayl hajmi juda katta (max {MAX_FILE_SIZE // (1024*1024)}MB).")
        return

    file_path = os.path.join(DOWNLOAD_DIR, f"{user_id}_{doc.file_id}.pdf")
    file = await bot.get_file(doc.file_id)
    await bot.download_file(file.file_path, file_path)

    status = await message.answer("🗜 PDF siqilmoqda...")
    output_path = os.path.join(DOWNLOAD_DIR, f"{user_id}_{doc.file_id}_compressed.pdf")

    try:
        stats = compress_pdf(file_path, output_path)
        old_size = stats["old_size"]
        new_size = stats["new_size"]
        images_processed = stats["images_processed"]
        saved = max(round(((old_size - new_size) / old_size) * 100, 1), 0)

        if new_size >= old_size:
            # Compression didn't help — send original back with message
            await message.answer(
                "ℹ️ Bu PDF allaqachon optimallashtirilgan — siqish imkoni yo'q."
            )
        else:
            result = FSInputFile(output_path, filename=user_pdf_filename(user))
            await bot.send_document(
                user_id, result,
                caption=(
                    f"✅ PDF siqildi!\n\n"
                    f"📦 Oldingi hajm: {old_size / 1024 / 1024:.2f} MB\n"
                    f"🗜 Yangi hajm: {new_size / 1024 / 1024:.2f} MB\n"
                    f"📉 Tejaldi: {saved}%\n"
                    f"🖼 Ishlov berilgan rasmlar: {images_processed}"
                )
            )
        inc_uses_and_log(user_id, "compress_pdf")
        logger.info(f"User {user_id}: compress_pdf (saved {saved}%)")
    except Exception as e:
        logger.error(f"Compress PDF error for user {user_id}: {e}")
        await message.answer(f"❌ PDF siqishda xatolik: {str(e)}")
    finally:
        safe_remove(file_path)
        safe_remove(output_path)
        try:
            await status.delete()
        except Exception:
            pass

    await show_main_menu(bot, message.chat.id)
