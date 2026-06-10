"""
Menu navigation and subscription check handlers.
"""
import logging

from aiogram import Router, Bot, F
from aiogram.types import CallbackQuery

from bot.config import CHANNEL_USER, FREE_USES_BEFORE_SUB
from bot.database import upsert_user, get_uses
from bot.keyboards import kb_main, kb_subscribe
from bot.states import (
    set_state, STATE_NONE, STATE_WAIT_TEXT,
    STATE_WAIT_IMG_PDF, STATE_WAIT_UPSCALE, STATE_WAIT_PDF_MERGE,
)

logger = logging.getLogger(__name__)
router = Router(name="menu")

WELCOME_TEXT = (
    "Assalamu Alaykum! 📌 Rasm yoki matnlaringizni PDF qiling "
    "va rasmlaringizni sifatini oshiring.\n"
    "Quyidan kerakli bo'limni tanlang:"
)


async def check_subscription(bot: Bot, user_id: int) -> bool:
    """Check if user is subscribed to the channel."""
    try:
        member = await bot.get_chat_member(chat_id=CHANNEL_USER, user_id=user_id)
        return member.status != "left"
    except Exception:
        return True


async def enforce_subscription(bot: Bot, user_id: int) -> bool:
    """Check if user can use the service."""
    uses = get_uses(user_id)
    if uses < FREE_USES_BEFORE_SUB:
        return True
    ok = await check_subscription(bot, user_id)
    if ok:
        return True
    await bot.send_message(
        user_id,
        f"Siz xizmatimizdan {FREE_USES_BEFORE_SUB} marta foydalandingiz.\n"
        "Yana foydalanish uchun kanalimizga obuna bo'ling 👇",
        reply_markup=kb_subscribe()
    )
    return False


async def show_main_menu(bot: Bot, chat_id: int, message_id: int = None):
    """Show or edit the main menu."""
    set_state(chat_id, STATE_NONE)
    if message_id:
        try:
            await bot.edit_message_text(
                WELCOME_TEXT, chat_id=chat_id, message_id=message_id, reply_markup=kb_main()
            )
            return
        except Exception:
            pass
    await bot.send_message(chat_id, WELCOME_TEXT, reply_markup=kb_main())


@router.callback_query(F.data == "act_cancel")
async def cb_cancel(call: CallbackQuery, bot: Bot):
    """Handle cancel/back to menu."""
    await call.answer()
    set_state(call.from_user.id, STATE_NONE)
    await show_main_menu(bot, call.message.chat.id, call.message.message_id)


@router.callback_query(F.data == "act_check_sub")
async def cb_check_sub(call: CallbackQuery, bot: Bot):
    """Handle subscription check button."""
    await call.answer()
    ok = await check_subscription(bot, call.from_user.id)
    if ok:
        await bot.send_message(call.from_user.id, "✅ Rahmat! Endi foydalanishingiz mumkin.")
        await show_main_menu(bot, call.message.chat.id, call.message.message_id)
    else:
        await bot.send_message(
            call.from_user.id,
            "❌ Hali obuna emassiz. Iltimos, kanalga obuna bo'ling.",
            reply_markup=kb_subscribe()
        )


@router.callback_query(F.data == "act_text_pdf")
async def cb_text_pdf(call: CallbackQuery, bot: Bot):
    """Start text-to-PDF flow."""
    await call.answer()
    user = call.from_user
    upsert_user(user.id, user.username, user.first_name, user.last_name)
    if not await enforce_subscription(bot, user.id):
        return
    set_state(user.id, STATE_WAIT_TEXT)
    from bot.keyboards import kb_cancel
    await bot.send_message(user.id, "📝 Matn yuboring (PDF qilib qaytaraman).",
                           reply_markup=kb_cancel())


@router.callback_query(F.data == "act_img_pdf")
async def cb_img_pdf(call: CallbackQuery, bot: Bot):
    """Start image-to-PDF flow."""
    await call.answer()
    user = call.from_user
    upsert_user(user.id, user.username, user.first_name, user.last_name)
    if not await enforce_subscription(bot, user.id):
        return
    set_state(user.id, STATE_WAIT_IMG_PDF)
    from bot.keyboards import kb_cancel
    await bot.send_message(user.id, "🖼 Rasm yuboring (bir yoki bir nechta).",
                           reply_markup=kb_cancel())


@router.callback_query(F.data == "act_upscale")
async def cb_upscale(call: CallbackQuery, bot: Bot):
    """Start upscale flow."""
    await call.answer()
    user = call.from_user
    upsert_user(user.id, user.username, user.first_name, user.last_name)
    if not await enforce_subscription(bot, user.id):
        return
    set_state(user.id, STATE_WAIT_UPSCALE)
    from bot.keyboards import kb_cancel
    await bot.send_message(user.id, "✨ Sifatini oshirish uchun rasm yuboring.",
                           reply_markup=kb_cancel())


@router.callback_query(F.data == "act_merge_pdf")
async def cb_merge_pdf(call: CallbackQuery, bot: Bot):
    """Start PDF merge flow."""
    await call.answer()
    user = call.from_user
    upsert_user(user.id, user.username, user.first_name, user.last_name)
    if not await enforce_subscription(bot, user.id):
        return
    set_state(user.id, STATE_WAIT_PDF_MERGE)
    from bot.keyboards import kb_cancel
    await bot.send_message(user.id, "📎 2 ta yoki undan ko'p PDF yuboring.",
                           reply_markup=kb_cancel())
