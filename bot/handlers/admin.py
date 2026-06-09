"""
Admin panel handlers: stats, top users, broadcast.
"""
import io
import asyncio
import logging
from datetime import datetime
from typing import Dict

from aiogram import Router, Bot, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, BufferedInputFile

from bot.config import ADMIN_IDS, BROADCAST_RATE
from bot.database import (
    upsert_user, get_admin_summary, daily_usage_by_action,
    get_top_users, get_active_users_24h, get_new_users_24h,
    get_all_user_ids, save_broadcast_result,
)
from bot.keyboards import kb_admin, kb_broadcast_confirm, kb_cancel
from bot.states import (
    set_state, get_state, STATE_NONE, STATE_WAIT_BROADCAST,
)
from bot.utils.chart import render_usage_chart_png

logger = logging.getLogger(__name__)
router = Router(name="admin")

# Broadcast state storage
PENDING_BROADCAST: Dict[int, dict] = {}
BROADCAST_RUNNING: Dict[int, bool] = {}


def _is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


def _format_user_row(r, index: int) -> str:
    uname = f"@{r['username']}" if r["username"] else "-"
    name = (f"{r['first_name'] or ''} {r.get('last_name', '') or ''}").strip() or "-"
    return f"{index}) {uname} | {name}"


# ========================
# COMMANDS
# ========================

@router.message(Command("admin"))
async def cmd_admin(message: Message, bot: Bot):
    """Admin panel with statistics."""
    if not _is_admin(message.from_user.id):
        return

    total_users, total_uses, active_24h, new_24h = get_admin_summary()
    text = (
        "🛠 Admin panel\n\n"
        f"👥 Jami foydalanuvchi: {total_users}\n"
        f"⚡️ Jami foydalanish: {total_uses}\n"
        f"🟢 Oxirgi 24 soat aktiv: {active_24h}\n"
        f"🆕 Oxirgi 24 soatda qo'shilgan: {new_24h}\n\n"
        "Quyidan bo'lim tanlang:"
    )
    try:
        data = daily_usage_by_action(7)
        png = render_usage_chart_png(data, "📊 So'nggi 7 kun")
        photo = BufferedInputFile(png, filename="usage_7d.png")
        await bot.send_photo(message.from_user.id, photo, caption=text, reply_markup=kb_admin())
    except Exception as e:
        logger.error(f"Admin panel chart error: {e}")
        await message.answer(text, reply_markup=kb_admin())


@router.message(Command("top"))
async def cmd_top(message: Message):
    """Show top 30 users."""
    if not _is_admin(message.from_user.id):
        return

    rows = get_top_users(30)
    lines = []
    for i, r in enumerate(rows, start=1):
        uname = f"@{r['username']}" if r["username"] else "-"
        name = (f"{r['first_name'] or ''} {r['last_name'] or ''}").strip() or "-"
        lines.append(f"{i}) {uname} | {name} | uses={r['uses_count']}")

    await message.answer("🏆 TOP-30:\n" + ("\n".join(lines) if lines else "—"))


@router.message(Command("broadcast"))
async def cmd_broadcast(message: Message):
    """Start broadcast mode."""
    if not _is_admin(message.from_user.id):
        return

    if BROADCAST_RUNNING.get(message.from_user.id):
        await message.answer("⚠️ Hozir broadcast davom etmoqda. Tugashini kuting.")
        return

    set_state(message.from_user.id, STATE_WAIT_BROADCAST)
    await message.answer(
        "📢 <b>Broadcast rejimi</b>\n\n"
        "Reklama xabarini yuboring:\n"
        "• 📸 <b>Rasm</b> (caption bilan yoki usiz)\n"
        "• 🎥 <b>Video</b> (caption bilan yoki usiz)\n"
        "• 📝 <b>Matn</b> (oddiy text xabar)\n\n"
        "Xabar barcha foydalanuvchilarga yuboriladi.",
        parse_mode="HTML",
        reply_markup=kb_cancel()
    )


# ========================
# BROADCAST CONTENT HANDLERS
# ========================

@router.message(lambda msg: msg.photo and get_state(msg.from_user.id) == STATE_WAIT_BROADCAST and msg.from_user.id in ADMIN_IDS)
async def broadcast_photo(message: Message, bot: Bot):
    """Receive photo for broadcast."""
    user_id = message.from_user.id
    photo = message.photo[-1]
    caption = message.caption or ""
    PENDING_BROADCAST[user_id] = {
        "media_type": "photo",
        "file_id": photo.file_id,
        "caption": caption,
    }
    user_count = len(get_all_user_ids())
    await bot.send_photo(
        user_id, photo.file_id,
        caption=(
            f"👁 <b>Preview</b>\n\n"
            f"📸 Rasm broadcast\n"
            f"📝 Caption: {caption or '(yo`q)'}\n"
            f"👥 {user_count} ta foydalanuvchiga yuboriladi\n\n"
            f"Tasdiqlaysizmi?"
        ),
        parse_mode="HTML",
        reply_markup=kb_broadcast_confirm()
    )


@router.message(lambda msg: msg.video and get_state(msg.from_user.id) == STATE_WAIT_BROADCAST and msg.from_user.id in ADMIN_IDS)
async def broadcast_video(message: Message, bot: Bot):
    """Receive video for broadcast."""
    user_id = message.from_user.id
    video = message.video
    caption = message.caption or ""
    PENDING_BROADCAST[user_id] = {
        "media_type": "video",
        "file_id": video.file_id,
        "caption": caption,
    }
    user_count = len(get_all_user_ids())
    await bot.send_video(
        user_id, video.file_id,
        caption=(
            f"👁 <b>Preview</b>\n\n"
            f"🎥 Video broadcast\n"
            f"📝 Caption: {caption or '(yo`q)'}\n"
            f"👥 {user_count} ta foydalanuvchiga yuboriladi\n\n"
            f"Tasdiqlaysizmi?"
        ),
        parse_mode="HTML",
        reply_markup=kb_broadcast_confirm()
    )


@router.message(lambda msg: msg.text and not msg.text.startswith("/") and get_state(msg.from_user.id) == STATE_WAIT_BROADCAST and msg.from_user.id in ADMIN_IDS)
async def broadcast_text(message: Message, bot: Bot):
    """Receive text for broadcast."""
    user_id = message.from_user.id
    text_content = message.text or ""
    PENDING_BROADCAST[user_id] = {
        "media_type": "text",
        "file_id": None,
        "caption": text_content,
    }
    user_count = len(get_all_user_ids())
    await message.answer(
        f"👁 <b>Preview</b>\n\n"
        f"📝 Matn broadcast:\n\n"
        f"<i>{text_content}</i>\n\n"
        f"👥 {user_count} ta foydalanuvchiga yuboriladi\n\n"
        f"Tasdiqlaysizmi?",
        parse_mode="HTML",
        reply_markup=kb_broadcast_confirm()
    )


# ========================
# BROADCAST CALLBACKS
# ========================

@router.callback_query(F.data == "broadcast_confirm")
async def cb_broadcast_confirm(call: CallbackQuery, bot: Bot):
    """Confirm and start broadcast."""
    await call.answer()
    admin_id = call.from_user.id
    if not _is_admin(admin_id):
        return

    data = PENDING_BROADCAST.pop(admin_id, None)
    if not data:
        await call.message.answer("⚠️ Broadcast ma'lumoti topilmadi. Qaytadan /broadcast yuboring.")
        return

    BROADCAST_RUNNING[admin_id] = True
    set_state(admin_id, STATE_NONE)

    user_count = len(get_all_user_ids())
    status_msg = await bot.send_message(
        admin_id, f"📡 Broadcast boshlandi...\n👥 {user_count} ta foydalanuvchiga yuboriladi."
    )

    asyncio.create_task(_do_broadcast(bot, admin_id, data, status_msg.message_id))

    try:
        await call.message.delete()
    except Exception:
        pass


@router.callback_query(F.data == "broadcast_cancel")
async def cb_broadcast_cancel(call: CallbackQuery, bot: Bot):
    """Cancel broadcast."""
    await call.answer()
    PENDING_BROADCAST.pop(call.from_user.id, None)
    set_state(call.from_user.id, STATE_NONE)
    try:
        await call.message.delete()
    except Exception:
        pass
    await bot.send_message(call.from_user.id, "❌ Broadcast bekor qilindi.")


# ========================
# ADMIN STAT CALLBACKS
# ========================

@router.callback_query(F.data == "admin_top30")
async def cb_admin_top30(call: CallbackQuery, bot: Bot):
    """Show top 30 users."""
    if not _is_admin(call.from_user.id):
        await call.answer()
        return
    await call.answer()
    rows = get_top_users(30)
    lines = []
    for i, r in enumerate(rows, start=1):
        uname = f"@{r['username']}" if r["username"] else "-"
        name = (f"{r['first_name'] or ''} {r['last_name'] or ''}").strip() or "-"
        lines.append(f"{i}) {uname} | {name} | uses={r['uses_count']}")
    await bot.send_message(call.from_user.id,
                           "🏆 TOP-30:\n" + ("\n".join(lines) if lines else "—"))


@router.callback_query(F.data == "admin_active24")
async def cb_admin_active24(call: CallbackQuery, bot: Bot):
    """Show active users in last 24h."""
    if not _is_admin(call.from_user.id):
        await call.answer()
        return
    await call.answer()
    rows = get_active_users_24h(30)
    lines = []
    for i, r in enumerate(rows, start=1):
        uname = f"@{r['username']}" if r["username"] else "-"
        name = (f"{r['first_name'] or ''} {r.get('last_name', '') or ''}").strip() or "-"
        lines.append(f"{i}) {uname} | {name} | {r['updated_at']}")
    await bot.send_message(call.from_user.id,
                           "🟢 Aktiv 24h:\n" + ("\n".join(lines) if lines else "—"))


@router.callback_query(F.data == "admin_new24")
async def cb_admin_new24(call: CallbackQuery, bot: Bot):
    """Show new users in last 24h."""
    if not _is_admin(call.from_user.id):
        await call.answer()
        return
    await call.answer()
    rows = get_new_users_24h(30)
    lines = []
    for i, r in enumerate(rows, start=1):
        uname = f"@{r['username']}" if r["username"] else "-"
        name = (f"{r['first_name'] or ''} {r.get('last_name', '') or ''}").strip() or "-"
        lines.append(f"{i}) {uname} | {name} | {r['created_at']}")
    await bot.send_message(call.from_user.id,
                           "🆕 Yangi 24h:\n" + ("\n".join(lines) if lines else "—"))


@router.callback_query(F.data == "admin_chart7")
async def cb_admin_chart7(call: CallbackQuery, bot: Bot):
    """Show 7-day usage chart."""
    if not _is_admin(call.from_user.id):
        await call.answer()
        return
    await call.answer()
    try:
        data = daily_usage_by_action(7)
        png = render_usage_chart_png(data, "📊 So'nggi 7 kun")
        photo = BufferedInputFile(png, filename="usage_7d.png")
        await bot.send_photo(call.from_user.id, photo, caption="📊 7 kunlik grafik")
    except Exception as e:
        logger.error(f"Chart error: {e}")
        await bot.send_message(call.from_user.id, "❌ Grafik yaratishda xatolik.")


# ========================
# BROADCAST ENGINE
# ========================

async def _do_broadcast(bot: Bot, admin_id: int, broadcast_data: dict, status_msg_id: int):
    """Execute broadcast to all users."""
    user_ids = get_all_user_ids()
    total = len(user_ids)
    success = 0
    failed = 0

    media_type = broadcast_data["media_type"]
    file_id = broadcast_data.get("file_id")
    caption = broadcast_data.get("caption", "")

    semaphore = asyncio.Semaphore(BROADCAST_RATE)

    async def send_one(uid: int):
        nonlocal success, failed
        async with semaphore:
            try:
                if media_type == "photo":
                    await bot.send_photo(uid, file_id, caption=caption or None)
                elif media_type == "video":
                    await bot.send_video(uid, file_id, caption=caption or None)
                else:
                    await bot.send_message(uid, caption)
                success += 1
            except Exception:
                failed += 1
            await asyncio.sleep(1 / BROADCAST_RATE)

    # Send in batches with progress updates
    batch_size = 50
    tasks = []
    for i, uid in enumerate(user_ids):
        tasks.append(send_one(uid))
        if len(tasks) >= batch_size:
            await asyncio.gather(*tasks)
            tasks = []
            try:
                await bot.edit_message_text(
                    f"📡 Yuborilmoqda...\n\n"
                    f"✅ Muvaffaqiyatli: {success}\n"
                    f"❌ Xato/Bloklagan: {failed}\n"
                    f"📊 Jami: {success + failed} / {total}",
                    chat_id=admin_id, message_id=status_msg_id
                )
            except Exception:
                pass

    if tasks:
        await asyncio.gather(*tasks)

    # Save result
    save_broadcast_result(admin_id, media_type, file_id or "", caption, total, success, failed)

    # Final report
    try:
        await bot.edit_message_text(
            f"✅ Broadcast tugadi!\n\n"
            f"👥 Jami foydalanuvchi: {total}\n"
            f"✅ Muvaffaqiyatli: {success}\n"
            f"🚫 Bloklagan/Xato: {failed}\n"
            f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            chat_id=admin_id, message_id=status_msg_id
        )
    except Exception:
        await bot.send_message(admin_id, f"✅ Broadcast tugadi! {success}/{total}")

    BROADCAST_RUNNING.pop(admin_id, None)
    logger.info(f"Broadcast complete: {success}/{total} success, {failed} failed")
