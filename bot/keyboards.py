"""
Inline keyboard markups for the bot.
"""
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from bot.config import CHANNEL_USER


def kb_main() -> InlineKeyboardMarkup:
    """Main menu keyboard."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📝 Matnni PDF qilish", callback_data="act_text_pdf")],
        [InlineKeyboardButton(text="🖼 Rasmni PDF qilish", callback_data="act_img_pdf")],
        [InlineKeyboardButton(text="✨ Rasm sifatini oshirish", callback_data="act_upscale")],
        [InlineKeyboardButton(text="📎 PDFlarni bitta qilish", callback_data="act_merge_pdf")],
    ])


def kb_cancel() -> InlineKeyboardMarkup:
    """Cancel / back to menu keyboard."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Bekor qilish / Bosh menyu", callback_data="act_cancel")],
    ])


def kb_subscribe() -> InlineKeyboardMarkup:
    """Subscription prompt keyboard."""
    channel_link = CHANNEL_USER.lstrip("@")
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 Kanalga obuna bo'lish", url=f"https://t.me/{channel_link}")],
        [InlineKeyboardButton(text="🔁 Tekshirish", callback_data="act_check_sub")],
    ])


def kb_admin() -> InlineKeyboardMarkup:
    """Admin panel keyboard."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📊 Statistika", callback_data="admin_stats"),
            InlineKeyboardButton(text="📈 7 kun grafik", callback_data="admin_chart7"),
        ],
        [
            InlineKeyboardButton(text="📉 30 kun o'sish", callback_data="admin_chart30"),
            InlineKeyboardButton(text="📋 Funksiya stat", callback_data="admin_actions"),
        ],
        [
            InlineKeyboardButton(text="🏆 TOP-30", callback_data="admin_top30"),
            InlineKeyboardButton(text="🆕 Yangi 24h", callback_data="admin_new24"),
        ],
        [
            InlineKeyboardButton(text="🔍 User qidirish", callback_data="admin_search"),
            InlineKeyboardButton(text="📜 Broadcast tarix", callback_data="admin_bc_history"),
        ],
        [
            InlineKeyboardButton(text="📢 Broadcast", callback_data="admin_broadcast"),
        ],
    ])


def kb_admin_back() -> InlineKeyboardMarkup:
    """Back to admin panel."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Admin panel", callback_data="admin_back")],
    ])


def kb_broadcast_confirm() -> InlineKeyboardMarkup:
    """Broadcast confirmation keyboard."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Ha, yubor", callback_data="broadcast_confirm"),
            InlineKeyboardButton(text="❌ Bekor qilish", callback_data="broadcast_cancel"),
        ],
    ])
