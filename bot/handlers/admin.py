"""
Admin panel handlers: stats as images, charts, user search, broadcast.
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
    get_top_users, get_new_users_24h,
    get_all_user_ids, save_broadcast_result,
    get_action_stats, get_growth_stats,
    get_broadcast_history, search_user,
)
from bot.keyboards import kb_admin, kb_admin_back, kb_broadcast_confirm, kb_cancel
from bot.states import set_state, get_state, STATE_NONE, STATE_WAIT_BROADCAST
from bot.utils.chart import render_usage_chart_png, render_growth_chart_png, render_stats_image

logger = logging.getLogger(__name__)
router = Router(name="admin")

# Broadcast state storage
PENDING_BROADCAST: Dict[int, dict] = {}
BROADCAST_RUNNING: Dict[int, bool] = {}

# Search state
STATE_WAIT_SEARCH = "wait_admin_search"


def _is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


# ========================
# COMMANDS
# ========================

@router.message(Command("admin"))
async def cmd_admin(message: Message, bot: Bot):
    """Admin panel — statistics as image."""
    if not _is_admin(message.from_user.id):
        return

    s = get_admin_summary()
    action_stats = get_action_stats()
    png = render_stats_image(s, action_stats)
    photo = BufferedInputFile(png, filename="stats.png")
    await bot.send_photo(
        message.from_user.id, photo,
        caption="🛠 <b>Admin Panel</b>\nQuyidan bo'lim tanlang:",
        parse_mode="HTML",
        reply_markup=kb_admin()
    )


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
        lines.append(f"{i}) {uname} | {name} | {r['uses_count']}")
    await message.answer(
        "<b>🏆 TOP-30:</b>\n\n" + ("\n".join(lines) if lines else "---"),
        parse_mode="HTML"
    )


@router.message(Command("broadcast"))
async def cmd_broadcast(message: Message):
    """Start broadcast mode."""
    if not _is_admin(message.from_user.id):
        return
    if BROADCAST_RUNNING.get(message.from_user.id):
        await message.answer("⚠️ Hozir broadcast davom etmoqda.")
        return
    set_state(message.from_user.id, STATE_WAIT_BROADCAST)
    await message.answer(
        "<b>📢 Broadcast rejimi</b>\n\n"
        "Reklama xabarini yuboring:\n"
        "• 📸 Rasm | 🎥 Video | 📝 Matn\n\n"
        "Barcha foydalanuvchilarga yuboriladi.",
        parse_mode="HTML",
        reply_markup=kb_cancel()
    )


@router.message(Command("search"))
async def cmd_search(message: Message, bot: Bot):
    """Search user by username/name/id."""
    if not _is_admin(message.from_user.id):
        return
    parts = message.text.split(maxsplit=1)
    if len(parts) > 1:
        await _do_search(message.from_user.id, parts[1].strip(), bot)
    else:
        set_state(message.from_user.id, STATE_WAIT_SEARCH)
        await message.answer(
            "🔍 Username, ism yoki user_id yuboring:",
            reply_markup=kb_admin_back()
        )


# ========================
# ADMIN CALLBACKS
# ========================

@router.callback_query(F.data == "admin_back")
async def cb_admin_back(call: CallbackQuery, bot: Bot):
    """Back to admin panel — show stats image."""
    await call.answer()
    if not _is_admin(call.from_user.id):
        return
    set_state(call.from_user.id, STATE_NONE)
    s = get_admin_summary()
    action_stats = get_action_stats()
    png = render_stats_image(s, action_stats)
    photo = BufferedInputFile(png, filename="stats.png")
    await bot.send_photo(
        call.from_user.id, photo,
        caption="🛠 <b>Admin Panel</b>\nBo'lim tanlang:",
        parse_mode="HTML",
        reply_markup=kb_admin()
    )


@router.callback_query(F.data == "admin_stats")
async def cb_admin_stats(call: CallbackQuery, bot: Bot):
    """Full statistics as image."""
    await call.answer()
    if not _is_admin(call.from_user.id):
        return
    s = get_admin_summary()
    action_stats = get_action_stats()
    png = render_stats_image(s, action_stats)
    photo = BufferedInputFile(png, filename="stats.png")
    await bot.send_photo(
        call.from_user.id, photo,
        caption="📊 Batafsil statistika",
        reply_markup=kb_admin_back()
    )


@router.callback_query(F.data == "admin_chart7")
async def cb_admin_chart7(call: CallbackQuery, bot: Bot):
    """7-day usage chart."""
    await call.answer()
    if not _is_admin(call.from_user.id):
        return
    try:
        data = daily_usage_by_action(7)
        png = render_usage_chart_png(data, "So'nggi 7 kun foydalanish")
        photo = BufferedInputFile(png, filename="usage_7d.png")
        await bot.send_photo(call.from_user.id, photo,
                             caption="📈 7 kunlik foydalanish grafigi",
                             reply_markup=kb_admin_back())
    except Exception as e:
        logger.error(f"Chart7 error: {e}")
        await bot.send_message(call.from_user.id, "❌ Grafik xatolik.",
                               reply_markup=kb_admin_back())


@router.callback_query(F.data == "admin_chart30")
async def cb_admin_chart30(call: CallbackQuery, bot: Bot):
    """30-day growth chart."""
    await call.answer()
    if not _is_admin(call.from_user.id):
        return
    try:
        growth = get_growth_stats(30)
        png = render_growth_chart_png(growth, "30 kunlik yangi foydalanuvchilar")
        photo = BufferedInputFile(png, filename="growth_30d.png")
        await bot.send_photo(call.from_user.id, photo,
                             caption="📉 30 kunlik o'sish grafigi",
                             reply_markup=kb_admin_back())
    except Exception as e:
        logger.error(f"Chart30 error: {e}")
        await bot.send_message(call.from_user.id, "❌ Grafik xatolik.",
                               reply_markup=kb_admin_back())


@router.callback_query(F.data == "admin_actions")
async def cb_admin_actions(call: CallbackQuery, bot: Bot):
    """Per-action statistics (included in stats image)."""
    await call.answer()
    if not _is_admin(call.from_user.id):
        return
    # Stats image already shows actions — redirect to full stats
    s = get_admin_summary()
    action_stats = get_action_stats()
    png = render_stats_image(s, action_stats)
    photo = BufferedInputFile(png, filename="actions.png")
    await bot.send_photo(call.from_user.id, photo,
                         caption="📋 Funksiyalar statistikasi",
                         reply_markup=kb_admin_back())


@router.callback_query(F.data == "admin_top30")
async def cb_admin_top30(call: CallbackQuery, bot: Bot):
    """Top 30 users."""
    await call.answer()
    if not _is_admin(call.from_user.id):
        return
    rows = get_top_users(30)
    lines = []
    for i, r in enumerate(rows, start=1):
        uname = f"@{r['username']}" if r["username"] else "-"
        name = (f"{r['first_name'] or ''} {r['last_name'] or ''}").strip() or "-"
        lines.append(f"{i}. {uname} | {name} | <b>{r['uses_count']}</b>")
    text = "<b>🏆 TOP-30:</b>\n\n" + ("\n".join(lines) if lines else "---")
    await bot.send_message(call.from_user.id, text, parse_mode="HTML",
                           reply_markup=kb_admin_back())


@router.callback_query(F.data == "admin_new24")
async def cb_admin_new24(call: CallbackQuery, bot: Bot):
    """New users 24h."""
    await call.answer()
    if not _is_admin(call.from_user.id):
        return
    rows = get_new_users_24h(30)
    lines = []
    for i, r in enumerate(rows, start=1):
        uname = f"@{r['username']}" if r["username"] else "-"
        name = (f"{r['first_name'] or ''}").strip() or "-"
        t = r["created_at"][11:16] if r["created_at"] and len(r["created_at"]) > 16 else ""
        lines.append(f"{i}. {uname} | {name} | {t}")
    text = "<b>🆕 Yangi 24 soat:</b>\n\n" + ("\n".join(lines) if lines else "Hech kim yo'q")
    await bot.send_message(call.from_user.id, text, parse_mode="HTML",
                           reply_markup=kb_admin_back())


@router.callback_query(F.data == "admin_bc_history")
async def cb_admin_bc_history(call: CallbackQuery, bot: Bot):
    """Broadcast history."""
    await call.answer()
    if not _is_admin(call.from_user.id):
        return
    rows = get_broadcast_history(10)
    if not rows:
        await bot.send_message(call.from_user.id, "📜 Broadcast tarixida hech narsa yo'q.",
                               reply_markup=kb_admin_back())
        return
    lines = []
    for r in rows:
        media = {"photo": "📸", "video": "🎥", "text": "📝"}.get(r["media_type"], "?")
        date = r["created_at"][:16] if r["created_at"] else "?"
        lines.append(
            f"{media} #{r['id']} | {date}\n"
            f"   ✅ {r['success']}/{r['total']} | ❌ {r['failed']}"
        )
    text = "<b>📜 Broadcast tarixi:</b>\n\n" + "\n\n".join(lines)
    await bot.send_message(call.from_user.id, text, parse_mode="HTML",
                           reply_markup=kb_admin_back())


@router.callback_query(F.data == "admin_search")
async def cb_admin_search(call: CallbackQuery, bot: Bot):
    """Start user search."""
    await call.answer()
    if not _is_admin(call.from_user.id):
        return
    set_state(call.from_user.id, STATE_WAIT_SEARCH)
    await bot.send_message(
        call.from_user.id,
        "🔍 Username, ism yoki user_id yuboring:",
        reply_markup=kb_admin_back()
    )


@router.callback_query(F.data == "admin_broadcast")
async def cb_admin_broadcast(call: CallbackQuery, bot: Bot):
    """Start broadcast from admin panel."""
    await call.answer()
    if not _is_admin(call.from_user.id):
        return
    if BROADCAST_RUNNING.get(call.from_user.id):
        await bot.send_message(call.from_user.id, "⚠️ Hozir broadcast davom etmoqda.")
        return
    set_state(call.from_user.id, STATE_WAIT_BROADCAST)
    await bot.send_message(
        call.from_user.id,
        "<b>📢 Broadcast</b>\n\nRasm, video yoki matn yuboring:",
        parse_mode="HTML",
        reply_markup=kb_cancel()
    )


# ========================
# SEARCH HANDLER
# ========================

@router.message(lambda msg: msg.text and not msg.text.startswith("/") and get_state(msg.from_user.id) == STATE_WAIT_SEARCH and msg.from_user.id in ADMIN_IDS)
async def handle_search(message: Message, bot: Bot):
    """Process user search query."""
    query = message.text.strip().lstrip("@")
    await _do_search(message.from_user.id, query, bot)


async def _do_search(admin_id: int, query: str, bot: Bot):
    """Execute user search and send results."""
    set_state(admin_id, STATE_NONE)
    rows = search_user(query)
    if not rows:
        await bot.send_message(
            admin_id,
            f"🔍 '<b>{query}</b>' bo'yicha topilmadi.",
            parse_mode="HTML",
            reply_markup=kb_admin_back()
        )
        return

    lines = []
    for r in rows:
        uname = f"@{r['username']}" if r["username"] else "-"
        name = (f"{r['first_name'] or ''} {r.get('last_name', '') or ''}").strip() or "-"
        lines.append(
            f"👤 <b>{name}</b> ({uname})\n"
            f"   ID: <code>{r['user_id']}</code>\n"
            f"   Foydalanish: {r['uses_count']} marta\n"
            f"   Ro'yxatdan: {str(r.get('created_at', ''))[:10]}"
        )

    text = f"🔍 Natijalar ({len(rows)}):\n\n" + "\n\n".join(lines)
    await bot.send_message(admin_id, text, parse_mode="HTML", reply_markup=kb_admin_back())


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
        f"📝 Matn:\n<i>{text_content}</i>\n\n"
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
        await call.message.answer("⚠️ Broadcast topilmadi. /broadcast yuboring.")
        return
    BROADCAST_RUNNING[admin_id] = True
    set_state(admin_id, STATE_NONE)
    user_count = len(get_all_user_ids())
    status_msg = await bot.send_message(
        admin_id, f"📡 Broadcast boshlandi... ({user_count} foydalanuvchi)"
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
    await bot.send_message(call.from_user.id, "❌ Bekor qilindi.", reply_markup=kb_admin_back())


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

    batch_size = 50
    tasks = []
    for uid in user_ids:
        tasks.append(send_one(uid))
        if len(tasks) >= batch_size:
            await asyncio.gather(*tasks)
            tasks = []
            try:
                await bot.edit_message_text(
                    f"📡 Yuborilmoqda...\n✅ {success} | ❌ {failed} | {success + failed}/{total}",
                    chat_id=admin_id, message_id=status_msg_id
                )
            except Exception:
                pass

    if tasks:
        await asyncio.gather(*tasks)

    save_broadcast_result(admin_id, media_type, file_id or "", caption, total, success, failed)

    try:
        await bot.edit_message_text(
            f"✅ <b>Broadcast tugadi!</b>\n\n"
            f"👥 Jami: {total}\n✅ Yuborildi: {success}\n🚫 Xato: {failed}\n"
            f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            chat_id=admin_id, message_id=status_msg_id,
            parse_mode="HTML"
        )
    except Exception:
        await bot.send_message(admin_id, f"✅ Broadcast: {success}/{total}")

    BROADCAST_RUNNING.pop(admin_id, None)
    logger.info(f"Broadcast: {success}/{total}, failed={failed}")
