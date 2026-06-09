import os
import io
import time
import re
import asyncio
import sqlite3
import subprocess
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from aiogram import Bot, Dispatcher, executor, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from PIL import Image
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from PyPDF2 import PdfMerger
import cv2
import fitz
import numpy as np

# ======================
#   ENV / SETTINGS
# ======================
# BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
BOT_TOKEN = "7621388113:AAFkj3TWO_w5FXYLdm2w8GUbNvn3GAJlX3U"
CHANNEL_USER = os.getenv("CHANNEL_USER", "@xonziyy").strip()

FREE_USES_BEFORE_SUB = int((os.getenv("FREE_USES_BEFORE_SUB", "15").strip() or "15"))

REAL_ESRGAN_BIN = os.getenv("REAL_ESRGAN_BIN", "").strip()
REAL_ESRGAN_MODELS = os.getenv("REAL_ESRGAN_MODELS", "").strip()
ENABLE_REAL_AI = os.getenv("ENABLE_REAL_AI", "1").strip() != "0"

ADMIN_IDS_RAW = os.getenv("ADMIN_IDS", "").strip()
ADMIN_ID_SINGLE = int(os.getenv("ADMIN_ID", "0") or "0")

DB_PATH = os.getenv("DB_PATH", "bot.db").strip() or "bot.db"
DOWNLOAD_DIR = os.getenv("DOWNLOAD_DIR", "downloads").strip() or "downloads"

CLEANUP_MAX_AGE_SECONDS = int(os.getenv("CLEANUP_MAX_AGE_SECONDS", str(24 * 3600)))
CLEANUP_INTERVAL_SECONDS = int(os.getenv("CLEANUP_INTERVAL_SECONDS", str(60 * 60)))

# Broadcast: bir sekundda nechta xabar yuborilsin (Telegram limit: ~30/s)
BROADCAST_RATE = int(os.getenv("BROADCAST_RATE", "25"))

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN topilmadi.")

os.makedirs(DOWNLOAD_DIR, exist_ok=True)


def parse_admin_ids(value: str) -> set:
    out = set()
    if value:
        for x in value.split(","):
            x = x.strip()
            if x.isdigit():
                out.add(int(x))
    if ADMIN_ID_SINGLE:
        out.add(int(ADMIN_ID_SINGLE))
    return out


ADMIN_IDS = parse_admin_ids(ADMIN_IDS_RAW)

# ======================
#   BOT INIT
# ======================
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)

# ======================
#   DB
# ======================
def db_connect():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def db_init():
    with db_connect() as con:
        cur = con.cursor()
        cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            last_name TEXT,
            uses_count INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        )
        """)
        cur.execute("""
        CREATE TABLE IF NOT EXISTS usage_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            action TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """)
        # ✅ Broadcast tarixini saqlash uchun jadval
        cur.execute("""
        CREATE TABLE IF NOT EXISTS broadcasts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            admin_id INTEGER NOT NULL,
            media_type TEXT,
            file_id TEXT,
            caption TEXT,
            total INTEGER DEFAULT 0,
            success INTEGER DEFAULT 0,
            failed INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now'))
        )
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_usage_user ON usage_logs(user_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_usage_date ON usage_logs(created_at)")
        con.commit()


def upsert_user(u: types.User):
    with db_connect() as con:
        con.execute("""
        INSERT INTO users (user_id, username, first_name, last_name, uses_count, created_at, updated_at)
        VALUES (?, ?, ?, ?, 0, datetime('now'), datetime('now'))
        ON CONFLICT(user_id) DO UPDATE SET
            username=excluded.username,
            first_name=excluded.first_name,
            last_name=excluded.last_name,
            updated_at=datetime('now')
        """, (u.id, u.username, u.first_name, u.last_name))
        con.commit()


def get_uses(user_id: int) -> int:
    with db_connect() as con:
        row = con.execute("SELECT uses_count FROM users WHERE user_id=?", (user_id,)).fetchone()
        return int(row["uses_count"]) if row and row["uses_count"] is not None else 0


def inc_uses_and_log(user_id: int, action: str):
    now = datetime.now(timezone.utc).isoformat()
    with db_connect() as con:
        con.execute(
            "UPDATE users SET uses_count = COALESCE(uses_count,0)+1, updated_at=datetime('now') WHERE user_id=?",
            (user_id,)
        )
        con.execute(
            "INSERT INTO usage_logs (user_id, action, created_at) VALUES (?, ?, ?)",
            (user_id, action, now)
        )
        con.commit()


def get_all_user_ids() -> List[int]:
    with db_connect() as con:
        rows = con.execute("SELECT user_id FROM users").fetchall()
        return [r["user_id"] for r in rows]


def save_broadcast_result(admin_id: int, media_type: str, file_id: str, caption: str,
                           total: int, success: int, failed: int):
    with db_connect() as con:
        con.execute("""
        INSERT INTO broadcasts (admin_id, media_type, file_id, caption, total, success, failed)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (admin_id, media_type, file_id, caption, total, success, failed))
        con.commit()


# ======================
#   STATE
# ======================
STATE_NONE = "none"
STATE_WAIT_TEXT = "wait_text"
STATE_WAIT_IMG_PDF = "wait_img_pdf"
STATE_WAIT_UPSCALE = "wait_upscale"
STATE_WAIT_PDF_MERGE = "wait_pdf_merge"
STATE_WAIT_WORD = "wait_word"
STATE_WAIT_BROADCAST = "wait_broadcast"  # ✅ Broadcast holati
STATE_WAIT_SMART_SCAN = "wait_smart_scan"
STATE_WAIT_COMPRESS_PDF = "wait_compress_pdf"

USER_STATE: Dict[int, str] = {}
MEDIA_BUFFER: Dict[Tuple[int, str], List[str]] = {}
MEDIA_TASK: Dict[Tuple[int, str], asyncio.Task] = {}
MENU_MESSAGE_ID: Dict[int, int] = {}

# Broadcast jarayoni davom etayotganini track qilish
BROADCAST_RUNNING: Dict[int, bool] = {}


def set_state(user_id: int, state: str):
    USER_STATE[user_id] = state


def get_state(user_id: int) -> str:
    return USER_STATE.get(user_id, STATE_NONE)


def safe_remove(path: str):
    try:
        if path and os.path.exists(path):
            os.remove(path)
    except Exception:
        pass


def _sanitize_filename_base(s: str) -> str:
    s = (s or "").strip()
    if not s:
        return ""
    out = []
    for ch in s:
        if ch.isalnum() or ch in ("_", "-", "."):
            out.append(ch)
        else:
            out.append("_")
    base = "".join(out).strip("._-")
    base = re.sub(r"_+", "_", base)
    return base[:40] if base else ""


def user_pdf_filename_from_user(u: types.User) -> str:
    base = _sanitize_filename_base(u.username or "") or _sanitize_filename_base(u.first_name or "") or f"user_{u.id}"
    return f"{base}.pdf"


def user_pdf_filename(user: types.User) -> str:
    base = _sanitize_filename_base(getattr(user, "username", "") or "") or \
           _sanitize_filename_base(getattr(user, "first_name", "") or "")
    if not base:
        base = f"user_{user.id}"
    return f"{base}.pdf"


# ======================
#   UI KEYBOARDS
# ======================
def kb_main() -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(
        InlineKeyboardButton("📝 Matnni PDF qilish", callback_data="act_text_pdf"),
        InlineKeyboardButton("🖼 Rasmni PDF qilish", callback_data="act_img_pdf"),
        InlineKeyboardButton("✨ Rasm sifatini oshirish", callback_data="act_upscale"),
        InlineKeyboardButton("📎 PDFlarni bitta qilish", callback_data="act_merge_pdf"),
        InlineKeyboardButton("🗜 PDF siqish", callback_data="act_compress_pdf"),
        InlineKeyboardButton("📄 Smart Scan", callback_data="act_smart_scan"),
    )
    return kb


def kb_cancel() -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(InlineKeyboardButton("⬅️ Bekor qilish / Bosh menyu", callback_data="act_cancel"))
    return kb


def kb_subscribe() -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(InlineKeyboardButton("📢 Kanalga obuna bo'lish", url=f"https://t.me/{CHANNEL_USER.lstrip('@')}"))
    kb.add(InlineKeyboardButton("🔁 Tekshirish", callback_data="act_check_sub"))
    return kb


def kb_admin() -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("🏆 TOP-30", callback_data="admin_top30"),
        InlineKeyboardButton("📈 7 kun grafik", callback_data="admin_chart7"),
    )
    kb.add(
        InlineKeyboardButton("🟢 Aktiv 24h", callback_data="admin_active24"),
        InlineKeyboardButton("🆕 Yangi 24h", callback_data="admin_new24"),
    )
    return kb


def kb_broadcast_confirm() -> InlineKeyboardMarkup:
    """Broadcast yuborishdan oldin tasdiqlash klaviaturasi."""
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("✅ Ha, yubor", callback_data="broadcast_confirm"),
        InlineKeyboardButton("❌ Bekor qilish", callback_data="broadcast_cancel"),
    )
    return kb


# ======================
#   BROADCAST STATE STORAGE
# ======================
# Admin yuborgan xabarni vaqtincha saqlash (confirm kutib)
PENDING_BROADCAST: Dict[int, dict] = {}
# {admin_id: {"media_type": "photo"|"video"|"text", "file_id": str|None, "caption": str}}


# ======================
#   ADMIN HELPERS
# ======================
def get_admin_summary():
    with db_connect() as con:
        total_users = con.execute("SELECT COUNT(*) c FROM users").fetchone()["c"]
        total_uses = con.execute("SELECT COALESCE(SUM(uses_count),0) s FROM users").fetchone()["s"]
        active_24h = con.execute("""
            SELECT COUNT(*) c FROM users
            WHERE updated_at >= datetime('now','-24 hours')
        """).fetchone()["c"]
        new_24h = con.execute("""
            SELECT COUNT(*) c FROM users
            WHERE created_at >= datetime('now','-24 hours')
        """).fetchone()["c"]
    return total_users, total_uses, active_24h, new_24h


def daily_usage_by_action(days: int = 7) -> Dict[str, Dict[str, int]]:
    with db_connect() as con:
        rows = con.execute(f"""
            SELECT substr(created_at, 1, 10) AS day, action, COUNT(*) AS cnt
            FROM usage_logs
            WHERE created_at >= datetime('now', '-{days} day')
            GROUP BY day, action
            ORDER BY day ASC
        """).fetchall()
    data: Dict[str, Dict[str, int]] = {}
    for r in rows:
        data.setdefault(r["day"], {})[r["action"]] = int(r["cnt"])
    return data


def render_action_stacked_chart_png(data: Dict[str, Dict[str, int]],
                                     title: str = "📈 7 kunlik foydalanish") -> bytes:
    W, H = 1150, 520
    pad_l, pad_r, pad_t, pad_b = 70, 40, 70, 70

    bg = Image.new("RGB", (W, H), (250, 250, 252))
    from PIL import ImageDraw, ImageFont
    d = ImageDraw.Draw(bg)

    try:
        font = ImageFont.truetype("DejaVuSans.ttf", 20)
        font_small = ImageFont.truetype("DejaVuSans.ttf", 14)
        font_tiny = ImageFont.truetype("DejaVuSans.ttf", 12)
    except Exception:
        font = ImageFont.load_default()
        font_small = ImageFont.load_default()
        font_tiny = ImageFont.load_default()

    d.text((pad_l, 18), title, fill=(20, 20, 25), font=font)

    if not data:
        d.text((pad_l, 110), "Ma'lumot yo'q.", fill=(50, 50, 60), font=font_small)
        buf = io.BytesIO()
        bg.save(buf, format="PNG")
        return buf.getvalue()

    days_list = list(data.keys())
    actions = ["text_pdf", "img_pdf", "upscale", "pdf_merge", "word_pdf"]
    colors = {
        "text_pdf": (59, 130, 246),
        "img_pdf": (16, 185, 129),
        "upscale": (245, 158, 11),
        "pdf_merge": (168, 85, 247),
        "word_pdf": (239, 68, 68),
    }
    labels = {
        "text_pdf": "Matn→PDF",
        "img_pdf": "Rasm→PDF",
        "upscale": "Upscale",
        "pdf_merge": "PDF merge",
        "word_pdf": "Word→PDF",
    }

    totals = []
    max_total = 0
    for day in days_list:
        t = sum(data.get(day, {}).get(a, 0) for a in actions)
        totals.append(t)
        max_total = max(max_total, t)
    max_total = max_total or 1

    x0, y0 = pad_l, pad_t
    x1, y1 = W - pad_r, H - pad_b
    plot_w = x1 - x0
    plot_h = y1 - y0

    d.rounded_rectangle([x0 - 10, y0 - 10, x1 + 10, y1 + 10],
                         radius=18, fill=(255, 255, 255), outline=(230, 230, 235), width=2)

    grid_n = 5
    for i in range(grid_n + 1):
        y = y1 - int(plot_h * i / grid_n)
        d.line((x0, y, x1, y), fill=(235, 235, 240), width=1)
        val = int(max_total * i / grid_n)
        d.text((x0 - 48, y - 8), str(val), fill=(120, 120, 130), font=font_tiny)

    n = len(days_list)
    gap = 10
    bar_w = min(max(18, int((plot_w - gap * (n - 1)) / max(n, 1))), 90)
    total_bars_w = bar_w * n + gap * (n - 1)
    start_x = x0 + max(0, (plot_w - total_bars_w) // 2)

    for i, day in enumerate(days_list):
        x = start_x + i * (bar_w + gap)
        y_base = y1
        for a in actions:
            v = data.get(day, {}).get(a, 0)
            if v <= 0:
                continue
            h = int(plot_h * (v / max_total))
            y_top = y_base - h
            d.rounded_rectangle([x, y_top, x + bar_w, y_base], radius=10, fill=colors[a])
            y_base = y_top
        d.text((x + 4, y_base - 18), str(totals[i]), fill=(40, 40, 45), font=font_tiny)
        day_lbl = day[5:] if len(day) >= 10 else day
        d.text((x, y1 + 10), day_lbl, fill=(90, 90, 100), font=font_tiny)

    lx = x1 - 320
    ly = pad_t - 52
    d.rounded_rectangle([lx, ly, x1, ly + 48], radius=14,
                         fill=(255, 255, 255), outline=(230, 230, 235), width=2)
    cx, cy = lx + 12, ly + 14
    for a in actions:
        d.rectangle([cx, cy, cx + 14, cy + 14], fill=colors[a])
        d.text((cx + 20, cy - 2), labels[a], fill=(40, 40, 45), font=font_tiny)
        cx += 66

    buf = io.BytesIO()
    bg.save(buf, format="PNG")
    return buf.getvalue()


# ======================
#   SUBSCRIPTION CHECK
# ======================
async def check_sub(user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(chat_id=CHANNEL_USER, user_id=user_id)
        return member.status != "left"
    except Exception:
        return True


async def enforce_rule_or_block(user_id: int) -> bool:
    uses = get_uses(user_id)
    if uses < FREE_USES_BEFORE_SUB:
        return True
    ok = await check_sub(user_id)
    if ok:
        return True
    try:
        await bot.send_message(
            user_id,
            f"Siz xizmatimizdan {FREE_USES_BEFORE_SUB} marta foydalandingiz.\n"
            "Yana foydalanish uchun kanalimizga obuna bo'ling 👇",
            reply_markup=kb_subscribe()
        )
    except Exception:
        pass
    return False


# ======================
#   PDF HELPERS
# ======================
def make_text_pdf_bytes(text: str) -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    width, height = A4
    margin = 50
    y = height - margin
    line_height = 14

    def wrap_line(s: str, max_chars: int = 95):
        s = s.strip("\n")
        if not s:
            return [""]
        out = []
        while len(s) > max_chars:
            cut = s.rfind(" ", 0, max_chars)
            if cut <= 0:
                cut = max_chars
            out.append(s[:cut].rstrip())
            s = s[cut:].lstrip()
        out.append(s)
        return out

    lines: List[str] = []
    for raw in text.splitlines():
        lines.extend(wrap_line(raw))

    c.setFont("Helvetica", 12)
    for line in lines:
        if y < margin:
            c.showPage()
            c.setFont("Helvetica", 12)
            y = height - margin
        c.drawString(margin, y, line)
        y -= line_height

    c.showPage()
    c.save()
    buf.seek(0)
    return buf.read()


def images_to_pdf(path_list: List[str], out_pdf_path: str):
    imgs = [Image.open(p).convert("RGB") for p in path_list]
    if not imgs:
        raise RuntimeError("no images")
    first, rest = imgs[0], imgs[1:]
    first.save(out_pdf_path, save_all=True, append_images=rest)


def merge_pdfs(pdf_paths: List[str], out_pdf_path: str):
    merger = PdfMerger()
    try:
        for p in pdf_paths:
            merger.append(p)
        with open(out_pdf_path, "wb") as f:
            merger.write(f)
    finally:
        try:
            merger.close()
        except Exception:
            pass


def compress_pdf(input_path: str, output_path: str):
    if not os.path.exists(input_path):
        raise FileNotFoundError("PDF topilmadi")

    doc = fitz.open(input_path)

    try:
        if doc.needs_pass:
            raise RuntimeError("Parolli PDF siqilmaydi")

        # Har bir page image recompress
        for page in doc:
            img_list = page.get_images(full=True)

            for img in img_list:
                xref = img[0]

                try:
                    base_image = doc.extract_image(xref)
                    image_bytes = base_image["image"]

                    img_np = np.frombuffer(image_bytes, np.uint8)
                    image = cv2.imdecode(img_np, cv2.IMREAD_COLOR)

                    if image is None:
                        continue

                    # JPEG recompress
                    _, compressed = cv2.imencode(
                        ".jpg",
                        image,
                        [cv2.IMWRITE_JPEG_QUALITY, 60]
                    )

                    doc.update_stream(
                        xref,
                        compressed.tobytes()
                    )

                except Exception:
                    continue

        doc.save(
            output_path,
            garbage=4,
            deflate=True,
            clean=True
        )

    finally:
        doc.close()

    if not os.path.exists(output_path):
        raise RuntimeError("PDF siqilmadi")


def convert_word_to_pdf(docx_path: str, out_pdf_path: str):
    out_dir = os.path.dirname(out_pdf_path)
    os.makedirs(out_dir, exist_ok=True)
    subprocess.run(
        ["soffice", "--headless", "--convert-to", "pdf", "--outdir", out_dir, docx_path],
        check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    produced = os.path.join(out_dir, os.path.splitext(os.path.basename(docx_path))[0] + ".pdf")
    if produced != out_pdf_path:
        if os.path.exists(out_pdf_path):
            safe_remove(out_pdf_path)
        os.rename(produced, out_pdf_path)

def smart_scan_document(input_path, output_path):
    image = cv2.imread(input_path)

    if image is None:
        raise Exception("Image topilmadi")

    original = image.copy()

    # Resize detection uchun
    ratio = image.shape[0] / 1000.0

    resized = cv2.resize(
        image,
        (
            int(image.shape[1] / ratio),
            1000
        )
    )

    gray = cv2.cvtColor(
        resized,
        cv2.COLOR_BGR2GRAY
    )

    # Blur noise kamaytirish
    blur = cv2.GaussianBlur(
        gray,
        (5, 5),
        0
    )

    # Edge detect
    edged = cv2.Canny(
        blur,
        50,
        150
    )

    contours, _ = cv2.findContours(
        edged.copy(),
        cv2.RETR_LIST,
        cv2.CHAIN_APPROX_SIMPLE
    )

    contours = sorted(
        contours,
        key=cv2.contourArea,
        reverse=True
    )[:10]

    doc_contour = None

    for contour in contours:
        peri = cv2.arcLength(
            contour,
            True
        )

        approx = cv2.approxPolyDP(
            contour,
            0.02 * peri,
            True
        )

        if len(approx) == 4:
            doc_contour = approx
            break

    # Agar qog'oz topilmasa original ishlaydi
    if doc_contour is None:
        cropped = original
    else:
        pts = doc_contour.reshape(4, 2) * ratio

        rect = np.zeros(
            (4, 2),
            dtype="float32"
        )

        s = pts.sum(axis=1)

        rect[0] = pts[np.argmin(s)]
        rect[2] = pts[np.argmax(s)]

        diff = np.diff(
            pts,
            axis=1
        )

        rect[1] = pts[np.argmin(diff)]
        rect[3] = pts[np.argmax(diff)]

        (tl, tr, br, bl) = rect

        widthA = np.linalg.norm(br - bl)
        widthB = np.linalg.norm(tr - tl)

        maxWidth = max(
            int(widthA),
            int(widthB)
        )

        heightA = np.linalg.norm(tr - br)
        heightB = np.linalg.norm(tl - bl)

        maxHeight = max(
            int(heightA),
            int(heightB)
        )

        dst = np.array([
            [0, 0],
            [maxWidth - 1, 0],
            [maxWidth - 1, maxHeight - 1],
            [0, maxHeight - 1]
        ], dtype="float32")

        matrix = cv2.getPerspectiveTransform(
            rect,
            dst
        )

        cropped = cv2.warpPerspective(
            original,
            matrix,
            (
                maxWidth,
                maxHeight
            )
        )

    # QUALITY ENHANCE
    gray = cv2.cvtColor(
        cropped,
        cv2.COLOR_BGR2GRAY
    )

    denoise = cv2.fastNlMeansDenoising(
        gray,
        None,
        8,
        7,
        21
    )

    clahe = cv2.createCLAHE(
        clipLimit=2.8,
        tileGridSize=(8, 8)
    )

    enhanced = clahe.apply(
        denoise
    )

    blur = cv2.GaussianBlur(
        enhanced,
        (0, 0),
        1.5
    )

    sharp = cv2.addWeighted(
        enhanced,
        1.65,
        blur,
        -0.65,
        0
    )

    # text clarity boost
    kernel = np.array([
        [-1, -1, -1],
        [-1, 9, -1],
        [-1, -1, -1]
    ])

    sharp = cv2.filter2D(
        sharp,
        -1,
        kernel
    )

    cv2.imwrite(
        output_path,
        sharp,
        [cv2.IMWRITE_JPEG_QUALITY, 95]
    )

# ======================
#   UPSCALE
# ======================
def pillow_upscale_2x(in_path: str, out_path: str):
    img = Image.open(in_path)
    new_size = (img.width * 2, img.height * 2)
    up = img.resize(new_size, Image.LANCZOS)
    up.save(out_path, quality=95, optimize=True)


def try_realesrgan(in_path: str, out_path: str) -> bool:
    if not ENABLE_REAL_AI:
        return False
    if not REAL_ESRGAN_BIN or not os.path.exists(REAL_ESRGAN_BIN):
        return False
    model_dir = REAL_ESRGAN_MODELS if REAL_ESRGAN_MODELS else "models"
    if REAL_ESRGAN_MODELS and not os.path.exists(REAL_ESRGAN_MODELS):
        return False
    cmd = [REAL_ESRGAN_BIN, "-i", in_path, "-o", out_path, "-s", "2",
           "-n", "realesrgan-x4plus", "-m", model_dir]
    try:
        p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                           text=True, timeout=180)
        return p.returncode == 0 and os.path.exists(out_path)
    except Exception:
        return False


# ======================
#   CLEANUP
# ======================
def cleanup_download_dir_once():
    try:
        now = time.time()
        for name in os.listdir(DOWNLOAD_DIR):
            path = os.path.join(DOWNLOAD_DIR, name)
            if not os.path.isfile(path):
                continue
            try:
                if now - os.path.getmtime(path) > CLEANUP_MAX_AGE_SECONDS:
                    safe_remove(path)
            except Exception:
                pass
    except Exception:
        pass


async def cleanup_worker():
    while True:
        cleanup_download_dir_once()
        await asyncio.sleep(CLEANUP_INTERVAL_SECONDS)


# ======================
#   BROADCAST ENGINE
# ======================
async def do_broadcast(admin_id: int, broadcast_data: dict, status_msg_id: int):
    """
    Barcha foydalanuvchilarga xabar yuboradi.
    broadcast_data = {
        "media_type": "photo" | "video" | "text",
        "file_id": str | None,
        "caption": str
    }
    """
    user_ids = get_all_user_ids()
    total = len(user_ids)
    success = 0
    failed = 0
    blocked = 0

    media_type = broadcast_data["media_type"]
    file_id = broadcast_data.get("file_id")
    caption = broadcast_data.get("caption", "")

    # Progress xabarini yangilash
    async def update_status():
        try:
            await bot.edit_message_text(
                f"📡 Yuborilmoqda...\n\n"
                f"✅ Muvaffaqiyatli: {success}\n"
                f"❌ Xato/Bloklagan: {failed}\n"
                f"📊 Jami: {success + failed} / {total}",
                chat_id=admin_id,
                message_id=status_msg_id
            )
        except Exception:
            pass

    semaphore = asyncio.Semaphore(BROADCAST_RATE)

    async def send_one(uid: int):
        nonlocal success, failed, blocked
        async with semaphore:
            try:
                if media_type == "photo":
                    await bot.send_photo(uid, file_id, caption=caption or None)
                elif media_type == "video":
                    await bot.send_video(uid, file_id, caption=caption or None)
                else:
                    await bot.send_message(uid, caption)
                success += 1
            except Exception as e:
                err = str(e).lower()
                if "blocked" in err or "deactivated" in err or "not found" in err:
                    blocked += 1
                failed += 1
            # Telegram flood limit uchun kichik pauza
            await asyncio.sleep(1 / BROADCAST_RATE)

    # Batch 50 tadan yuborish + har 50 ta progress yangilash
    batch_size = 50
    tasks = []
    for i, uid in enumerate(user_ids):
        tasks.append(send_one(uid))
        if len(tasks) >= batch_size:
            await asyncio.gather(*tasks)
            tasks = []
            await update_status()

    if tasks:
        await asyncio.gather(*tasks)

    # Natijani saqlash
    save_broadcast_result(admin_id, media_type, file_id or "", caption, total, success, failed)

    # Yakuniy hisobot
    try:
        await bot.edit_message_text(
            f"✅ Broadcast tugadi!\n\n"
            f"👥 Jami foydalanuvchi: {total}\n"
            f"✅ Muvaffaqiyatli: {success}\n"
            f"🚫 Bloklagan/Xato: {failed}\n"
            f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            chat_id=admin_id,
            message_id=status_msg_id
        )
    except Exception:
        try:
            await bot.send_message(
                admin_id,
                f"✅ Broadcast tugadi! Muvaffaqiyatli: {success}/{total}"
            )
        except Exception:
            pass

    BROADCAST_RUNNING.pop(admin_id, None)


# ======================
#   MAIN MENU
# ======================
async def show_main_menu(chat_id: int, message_id: Optional[int] = None):
    set_state(chat_id, STATE_NONE)
    text = ("Assalamu Alaykum! 📌 Rasm yoki matnlaringizni PDF qiling "
            "va rasmlaringizni sifatini oshiring.\nQuyidan kerakli bo'limni tanlang:")
    kb = kb_main()
    mid = message_id or MENU_MESSAGE_ID.get(chat_id)
    if mid:
        try:
            await bot.edit_message_text(text, chat_id=chat_id, message_id=mid, reply_markup=kb)
            MENU_MESSAGE_ID[chat_id] = mid
            return
        except Exception:
            pass
    try:
        msg = await bot.send_message(chat_id, text, reply_markup=kb)
        MENU_MESSAGE_ID[chat_id] = msg.message_id
    except Exception:
        pass


async def show_step_from_call(call: types.CallbackQuery, text: str,
                               reply_markup: InlineKeyboardMarkup):
    chat_id = call.message.chat.id if call.message else call.from_user.id
    mid = call.message.message_id if call.message else MENU_MESSAGE_ID.get(chat_id)
    if mid:
        try:
            await bot.edit_message_text(text, chat_id=chat_id, message_id=mid,
                                         reply_markup=reply_markup)
            MENU_MESSAGE_ID[chat_id] = mid
            return
        except Exception:
            pass
    try:
        msg = await bot.send_message(chat_id, text, reply_markup=reply_markup)
        MENU_MESSAGE_ID[chat_id] = msg.message_id
    except Exception:
        pass


# ======================
#   COMMANDS
# ======================
@dp.message_handler(commands=["start"])
async def cmd_start(message: types.Message):
    upsert_user(message.from_user)
    await show_main_menu(message.chat.id)


@dp.message_handler(commands=["admin"])
async def cmd_admin(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
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
        png = render_action_stacked_chart_png(data, "📊 So'nggi 7 kun")
        await bot.send_photo(
            message.from_user.id,
            types.InputFile(io.BytesIO(png), filename="usage_7d.png"),
            caption=text,
            reply_markup=kb_admin()
        )
    except Exception:
        await message.answer(text, reply_markup=kb_admin())


@dp.message_handler(commands=["top"])
async def cmd_top(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    with db_connect() as con:
        rows = con.execute("""
            SELECT user_id, COALESCE(username,''), COALESCE(first_name,''),
                   COALESCE(last_name,''), uses_count
            FROM users ORDER BY uses_count DESC, updated_at DESC LIMIT 30
        """).fetchall()

    def fmt(r):
        uname = f"@{r[1]}" if r[1] else "-"
        name = (f"{r[2] or ''} {r[3] or ''}").strip() or "-"
        return f"{uname} | {name} | uses={r[4]}"

    lines = [f"{i}) {fmt(r)}" for i, r in enumerate(rows, start=1)]
    await message.answer("🏆 TOP-30:\n" + ("\n".join(lines) if lines else "—"))


# ✅ BROADCAST COMMAND
@dp.message_handler(commands=["broadcast"])
async def cmd_broadcast(message: types.Message):
    """
    Admin /broadcast buyrug'ini yuboradi.
    Keyin rasm, video yoki matn yuboradi — bot tasdiqlash so'raydi.
    """
    if message.from_user.id not in ADMIN_IDS:
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


# ======================
#   CALLBACKS
# ======================
@dp.callback_query_handler(text="act_cancel")
async def cb_cancel(call: types.CallbackQuery):
    await call.answer()
    # Broadcast pending bo'lsa tozalash
    PENDING_BROADCAST.pop(call.from_user.id, None)
    await show_main_menu(
        call.message.chat.id if call.message else call.from_user.id,
        call.message.message_id if call.message else None
    )


@dp.callback_query_handler(text="act_check_sub")
async def cb_check_sub(call: types.CallbackQuery):
    await call.answer()
    ok = await check_sub(call.from_user.id)
    if ok:
        try:
            await bot.send_message(call.from_user.id, "✅ Rahmat! Endi foydalanishingiz mumkin.")
        except Exception:
            pass
        await show_main_menu(
            call.message.chat.id if call.message else call.from_user.id,
            call.message.message_id if call.message else None
        )
    else:
        try:
            await bot.send_message(
                call.from_user.id,
                "❌ Hali obuna emassiz. Iltimos, kanalga obuna bo'ling.",
                reply_markup=kb_subscribe()
            )
        except Exception:
            pass

@dp.callback_query_handler(text="act_compress_pdf")
async def cb_compress_pdf(call: types.CallbackQuery):
    await call.answer()

    upsert_user(call.from_user)

    if not await enforce_rule_or_block(call.from_user.id):
        return

    set_state(
        call.from_user.id,
        STATE_WAIT_COMPRESS_PDF
    )

    await bot.send_message(
        call.from_user.id,
        "🗜 PDF yuboring.\n\nMen hajmini kichraytiraman.",
        reply_markup=kb_cancel()
    )


# ✅ Broadcast tasdiqlash
@dp.callback_query_handler(text="broadcast_confirm")
async def cb_broadcast_confirm(call: types.CallbackQuery):
    await call.answer()
    admin_id = call.from_user.id
    if admin_id not in ADMIN_IDS:
        return

    data = PENDING_BROADCAST.pop(admin_id, None)
    if not data:
        await call.message.answer("⚠️ Broadcast ma'lumoti topilmadi. Qaytadan /broadcast yuboring.")
        return

    BROADCAST_RUNNING[admin_id] = True
    set_state(admin_id, STATE_NONE)

    user_count = len(get_all_user_ids())
    try:
        status_msg = await bot.send_message(
            admin_id,
            f"📡 Broadcast boshlandi...\n👥 {user_count} ta foydalanuvchiga yuboriladi."
        )
    except Exception:
        status_msg = None

    # Background task sifatida ishga tushir
    if status_msg:
        asyncio.create_task(do_broadcast(admin_id, data, status_msg.message_id))
    else:
        asyncio.create_task(do_broadcast(admin_id, data, 0))

    # Preview xabarini o'chirish
    try:
        await call.message.delete()
    except Exception:
        pass


@dp.callback_query_handler(text="broadcast_cancel")
async def cb_broadcast_cancel(call: types.CallbackQuery):
    await call.answer()
    PENDING_BROADCAST.pop(call.from_user.id, None)
    set_state(call.from_user.id, STATE_NONE)
    try:
        await call.message.delete()
    except Exception:
        pass
    await bot.send_message(call.from_user.id, "❌ Broadcast bekor qilindi.")


@dp.callback_query_handler(text="admin_top30")
async def cb_admin_top30(call: types.CallbackQuery):
    if call.from_user.id not in ADMIN_IDS:
        await call.answer()
        return
    await call.answer()
    with db_connect() as con:
        rows = con.execute("""
            SELECT user_id, COALESCE(username,''), COALESCE(first_name,''),
                   COALESCE(last_name,''), uses_count
            FROM users ORDER BY uses_count DESC, updated_at DESC LIMIT 30
        """).fetchall()

    def fmt(r):
        uname = f"@{r[1]}" if r[1] else "-"
        name = (f"{r[2] or ''} {r[3] or ''}").strip() or "-"
        return f"{uname} | {name} | uses={r[4]}"

    lines = [f"{i}) {fmt(r)}" for i, r in enumerate(rows, start=1)]
    try:
        await bot.send_message(call.from_user.id,
                               "🏆 TOP-30:\n" + ("\n".join(lines) if lines else "—"))
    except Exception:
        pass


@dp.callback_query_handler(text="admin_active24")
async def cb_admin_active24(call: types.CallbackQuery):
    if call.from_user.id not in ADMIN_IDS:
        await call.answer()
        return
    await call.answer()
    with db_connect() as con:
        rows = con.execute("""
            SELECT user_id, COALESCE(username,''), COALESCE(first_name,''),
                   COALESCE(last_name,''), updated_at
            FROM users WHERE updated_at >= datetime('now','-24 hours')
            ORDER BY updated_at DESC LIMIT 30
        """).fetchall()

    def fmt(r):
        uname = f"@{r[1]}" if r[1] else "-"
        name = (f"{r[2] or ''} {r[3] or ''}").strip() or "-"
        return f"{uname} | {name} | {r[4]}"

    lines = [f"{i}) {fmt(r)}" for i, r in enumerate(rows, start=1)]
    try:
        await bot.send_message(call.from_user.id,
                               "🟢 Aktiv 24h:\n" + ("\n".join(lines) if lines else "—"))
    except Exception:
        pass


@dp.callback_query_handler(text="admin_new24")
async def cb_admin_new24(call: types.CallbackQuery):
    if call.from_user.id not in ADMIN_IDS:
        await call.answer()
        return
    await call.answer()
    with db_connect() as con:
        rows = con.execute("""
            SELECT user_id, COALESCE(username,''), COALESCE(first_name,''),
                   COALESCE(last_name,''), created_at
            FROM users WHERE created_at >= datetime('now','-24 hours')
            ORDER BY created_at DESC LIMIT 30
        """).fetchall()

    def fmt(r):
        uname = f"@{r[1]}" if r[1] else "-"
        name = (f"{r[2] or ''} {r[3] or ''}").strip() or "-"
        return f"{uname} | {name} | {r[4]}"

    lines = [f"{i}) {fmt(r)}" for i, r in enumerate(rows, start=1)]
    try:
        await bot.send_message(call.from_user.id,
                               "🆕 Yangi 24h:\n" + ("\n".join(lines) if lines else "—"))
    except Exception:
        pass


@dp.callback_query_handler(text="admin_chart7")
async def cb_admin_chart7(call: types.CallbackQuery):
    if call.from_user.id not in ADMIN_IDS:
        await call.answer()
        return
    await call.answer()
    try:
        data = daily_usage_by_action(7)
        png = render_action_stacked_chart_png(data, "📊 So'nggi 7 kun")
        await bot.send_photo(
            call.from_user.id,
            types.InputFile(io.BytesIO(png), filename="usage_7d.png"),
            caption="📊 7 kunlik grafik"
        )
    except Exception:
        pass

@dp.callback_query_handler(text="act_smart_scan")
async def cb_smart_scan(call: types.CallbackQuery):
    await call.answer()

    upsert_user(call.from_user)

    if not await enforce_rule_or_block(call.from_user.id):
        return

    set_state(call.from_user.id, STATE_WAIT_SMART_SCAN)

    try:
        await bot.send_message(
            call.from_user.id,
            "📄 Document rasmini yuboring.\n\nMen uni professional scan qilib beraman.",
            reply_markup=kb_cancel()
        )
    except Exception:
        pass

@dp.callback_query_handler(text="act_text_pdf")
async def cb_text_pdf(call: types.CallbackQuery):
    await call.answer()
    upsert_user(call.from_user)
    if not await enforce_rule_or_block(call.from_user.id):
        return
    set_state(call.from_user.id, STATE_WAIT_TEXT)
    try:
        await show_step_from_call(call, "📝 Matn yuboring (PDF qilib qaytaraman).", kb_cancel())
    except Exception:
        pass


@dp.callback_query_handler(text="act_img_pdf")
async def cb_img_pdf(call: types.CallbackQuery):
    await call.answer()
    upsert_user(call.from_user)
    if not await enforce_rule_or_block(call.from_user.id):
        return
    set_state(call.from_user.id, STATE_WAIT_IMG_PDF)
    try:
        await bot.send_message(call.from_user.id, "🖼 Rasm yuboring.", reply_markup=kb_cancel())
    except Exception:
        pass


@dp.callback_query_handler(text="act_upscale")
async def cb_upscale(call: types.CallbackQuery):
    await call.answer()
    upsert_user(call.from_user)
    if not await enforce_rule_or_block(call.from_user.id):
        return
    set_state(call.from_user.id, STATE_WAIT_UPSCALE)
    try:
        await bot.send_message(call.from_user.id, "✨ Sifatini oshirish uchun rasm yuboring.",
                               reply_markup=kb_cancel())
    except Exception:
        pass


@dp.callback_query_handler(text="act_merge_pdf")
async def cb_merge_pdf(call: types.CallbackQuery):
    await call.answer()
    upsert_user(call.from_user)
    if not await enforce_rule_or_block(call.from_user.id):
        return
    set_state(call.from_user.id, STATE_WAIT_PDF_MERGE)
    try:
        await bot.send_message(
            call.from_user.id,
            "📎 2 ta yoki undan ko'p PDF yuboring.",
            reply_markup=kb_cancel()
        )
    except Exception:
        pass


@dp.callback_query_handler(text="act_word_pdf")
async def cb_word_pdf(call: types.CallbackQuery):
    await call.answer()
    upsert_user(call.from_user)
    if not await enforce_rule_or_block(call.from_user.id):
        return
    set_state(call.from_user.id, STATE_WAIT_WORD)
    try:
        await bot.send_message(
            call.from_user.id,
            "📄 Word fayl (.docx) yuboring — PDF qilib qaytaraman.",
            reply_markup=kb_cancel()
        )
    except Exception:
        pass


# ======================
#   MESSAGE HANDLERS
# ======================

# ✅ BROADCAST: PHOTO handler
@dp.message_handler(content_types=["photo"],
                    state=None)  # state filter yo'q, get_state bilan tekshiramiz
async def on_photo(message: types.Message):
    upsert_user(message.from_user)
    user_id = message.from_user.id
    st = get_state(user_id)

    # ✅ Broadcast uchun rasm
    if st == STATE_WAIT_BROADCAST and user_id in ADMIN_IDS:
        photo = message.photo[-1]
        caption = message.caption or ""
        PENDING_BROADCAST[user_id] = {
            "media_type": "photo",
            "file_id": photo.file_id,
            "caption": caption,
        }
        # Preview ko'rsatish
        user_count = len(get_all_user_ids())
        caption_preview = caption or "(yo'q)"
        preview_caption = (
            f"👁 <b>Preview</b>\n\n"
            f"📸 Rasm broadcast\n"
            f"📝 Caption: {caption_preview}\n"
            f"👥 {user_count} ta foydalanuvchiga yuboriladi\n\n"
            f"Tasdiqlaysizmi?"
        )
        await bot.send_photo(
            user_id, photo.file_id,
            caption=preview_caption,
            parse_mode="HTML",
            reply_markup=kb_broadcast_confirm()
        )
        return

    # Oddiy holat
    if st not in (STATE_WAIT_IMG_PDF, STATE_WAIT_UPSCALE, STATE_WAIT_SMART_SCAN):
        return
    if not await enforce_rule_or_block(user_id):
        return

    try:
        photo = message.photo[-1]
        file_path = os.path.join(DOWNLOAD_DIR, f"{user_id}_{photo.file_id}.jpg")
        await photo.download(destination=file_path)
    except Exception:
        return

    if st == STATE_WAIT_SMART_SCAN:
        try:
            status = await message.answer(
                "📄 Document scan qilinmoqda..."
            )
        except Exception:
            status = None

        out_path = os.path.join(
            DOWNLOAD_DIR,
            f"{user_id}_{photo.file_id}_scan.jpg"
        )

        try:
            smart_scan_document(
                file_path,
                out_path
            )

            with open(out_path, "rb") as f:
                await bot.send_document(
                    user_id,
                    f,
                    caption="✅ Smart scan tayyor!"
                )

            inc_uses_and_log(
                user_id,
                "smart_scan"
            )

        except Exception as e:
            await message.answer(
                f"❌ Error: {str(e)}"
            )

        finally:
            safe_remove(file_path)
            safe_remove(out_path)

            if status:
                try:
                    await bot.delete_message(
                        user_id,
                        status.message_id
                    )
                except Exception:
                    pass

        await show_main_menu(user_id)
        return

    if st == STATE_WAIT_UPSCALE:
        try:
            status = await message.answer("⏳ Sifat oshirilmoqda...")
        except Exception:
            status = None
        out_path = os.path.join(DOWNLOAD_DIR, f"{user_id}_{photo.file_id}_up.jpg")
        try:
            ok = try_realesrgan(file_path, out_path)
            if not ok:
                pillow_upscale_2x(file_path, out_path)
            with open(out_path, "rb") as f:
                await bot.send_photo(user_id, f, caption="✅ Tayyor!")
            inc_uses_and_log(user_id, "upscale")
        except Exception:
            pass
        finally:
            safe_remove(file_path)
            safe_remove(out_path)
            if status:
                try:
                    await bot.delete_message(user_id, status.message_id)
                except Exception:
                    pass
        await show_main_menu(user_id)
        return

    # IMG → PDF
    if message.media_group_id:
        key = (user_id, message.media_group_id)
        MEDIA_BUFFER.setdefault(key, []).append(file_path)
        old_task = MEDIA_TASK.get(key)
        if old_task and not old_task.done():
            old_task.cancel()

        async def finalize_group():
            await asyncio.sleep(1.2)
            paths = MEDIA_BUFFER.pop(key, [])
            MEDIA_TASK.pop(key, None)
            if not paths:
                return
            try:
                status = await bot.send_message(user_id, "⏳ PDF tayyorlanmoqda...")
            except Exception:
                status = None
            pdf_path = os.path.join(DOWNLOAD_DIR, f"images_{user_id}_{int(time.time())}.pdf")
            try:
                images_to_pdf(paths, pdf_path)
                with open(pdf_path, "rb") as f:
                    await bot.send_document(
                        user_id,
                        types.InputFile(f.name, filename=user_pdf_filename(message.from_user)),
                        caption="✅ Tayyor!"
                    )
                inc_uses_and_log(user_id, "img_pdf")
            except Exception:
                pass
            finally:
                for p in paths:
                    safe_remove(p)
                safe_remove(pdf_path)
                if status:
                    try:
                        await bot.delete_message(user_id, status.message_id)
                    except Exception:
                        pass
            await show_main_menu(user_id)

        MEDIA_TASK[key] = asyncio.create_task(finalize_group())
        return

    try:
        status = await message.answer("⏳ PDF tayyorlanmoqda...")
    except Exception:
        status = None
    pdf_path = os.path.join(DOWNLOAD_DIR, f"image_{user_id}_{int(time.time())}.pdf")
    try:
        images_to_pdf([file_path], pdf_path)
        with open(pdf_path, "rb") as f:
            await bot.send_document(
                user_id,
                types.InputFile(f.name, filename=user_pdf_filename(message.from_user)),
                caption="✅ Tayyor!"
            )
        inc_uses_and_log(user_id, "img_pdf")
    except Exception:
        pass
    finally:
        safe_remove(file_path)
        safe_remove(pdf_path)
        if status:
            try:
                await bot.delete_message(user_id, status.message_id)
            except Exception:
                pass
    await show_main_menu(user_id)


# ✅ BROADCAST: VIDEO handler
@dp.message_handler(content_types=["video"])
async def on_video(message: types.Message):
    upsert_user(message.from_user)
    user_id = message.from_user.id
    st = get_state(user_id)

    if st == STATE_WAIT_BROADCAST and user_id in ADMIN_IDS:
        video = message.video
        caption = message.caption or ""
        PENDING_BROADCAST[user_id] = {
            "media_type": "video",
            "file_id": video.file_id,
            "caption": caption,
        }
        user_count = len(get_all_user_ids())
        caption_preview = caption or "(yo'q)"
        preview_caption = (
            f"👁 <b>Preview</b>\n\n"
            f"🎥 Video broadcast\n"
            f"📝 Caption: {caption_preview}\n"
            f"👥 {user_count} ta foydalanuvchiga yuboriladi\n\n"
            f"Tasdiqlaysizmi?"
        )
        await bot.send_video(
            user_id, video.file_id,
            caption=preview_caption,
            parse_mode="HTML",
            reply_markup=kb_broadcast_confirm()
        )
        return


# ✅ TEXT handler (broadcast + oddiy)
@dp.message_handler(content_types=["text"])
async def on_text(message: types.Message):
    upsert_user(message.from_user)
    user_id = message.from_user.id
    st = get_state(user_id)

    # Broadcast text rejimi
    if st == STATE_WAIT_BROADCAST and user_id in ADMIN_IDS:
        # /broadcast o'zi command bo'lgani uchun, text xabar = reklama matni
        text_content = message.text or ""
        if text_content.startswith("/"):
            return  # boshqa command bo'lsa o'tkazib yuborish
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
        return

    # Oddiy holat
    if st != STATE_WAIT_TEXT:
        return
    if not await enforce_rule_or_block(user_id):
        return

    text = (message.text or "").strip()
    if not text:
        return

    try:
        status = await message.answer("⏳ PDF tayyorlanmoqda...")
    except Exception:
        status = None
    try:
        pdf_bytes = make_text_pdf_bytes(text)
        file_name = user_pdf_filename_from_user(message.from_user)
        await bot.send_document(
            user_id,
            types.InputFile(io.BytesIO(pdf_bytes), filename=file_name),
            caption="✅ Tayyor!"
        )
        inc_uses_and_log(user_id, "text_pdf")
    except Exception:
        pass
    finally:
        if status:
            try:
                await bot.delete_message(user_id, status.message_id)
            except Exception:
                pass
    await show_main_menu(message.chat.id)


@dp.message_handler(content_types=["document"])
async def on_document(message: types.Message):
    upsert_user(message.from_user)
    user_id = message.from_user.id
    st = get_state(user_id)

    if st == STATE_WAIT_COMPRESS_PDF:
        if not await enforce_rule_or_block(user_id):
            return

        doc = message.document

        file_name = (doc.file_name or "").lower()
        if doc.mime_type != "application/pdf" and not file_name.endswith(".pdf"):
            await message.answer(
                "❌ Faqat PDF yuboring."
            )
            return

        status = await message.answer(
            "📉 PDF siqilmoqda..."
        )

        input_path = os.path.join(
            DOWNLOAD_DIR,
            f"{user_id}_{doc.file_id}.pdf"
        )

        output_path = os.path.join(
            DOWNLOAD_DIR,
            f"{user_id}_{doc.file_id}_compressed.pdf"
        )

        await doc.download(destination_file=input_path)

        try:
            old_size = os.path.getsize(input_path)

            compress_pdf(
                input_path,
                output_path
            )

            new_size = os.path.getsize(output_path)

            saved = max(round(((old_size - new_size) / old_size) * 100, 1), 0)

            with open(output_path, "rb") as f:
                await bot.send_document(
                    user_id,
                    types.InputFile(f.name, filename=user_pdf_filename(message.from_user)),
                    caption=(
                        f"✅ PDF siqildi!\n\n"
                        f"📦 Old size: {old_size / 1024 / 1024:.2f} MB\n"
                        f"🗜 New size: {new_size / 1024 / 1024:.2f} MB\n"
                        f"📉 Saved: {saved}%"
                    )
                )

            inc_uses_and_log(
                user_id,
                "compress_pdf"
            )

        except Exception as e:
            await message.answer(
                f"❌ Error: {str(e)}"
            )

        finally:
            safe_remove(input_path)
            safe_remove(output_path)

            try:
                await bot.delete_message(
                    user_id,
                    status.message_id
                )
            except Exception:
                pass

        await show_main_menu(user_id)
        return

    # PDF MERGE
    if st != STATE_WAIT_PDF_MERGE:
        return
    if not await enforce_rule_or_block(user_id):
        return
    doc = message.document
    if not doc:
        return
    if doc.mime_type != "application/pdf" and not (doc.file_name or "").lower().endswith(".pdf"):
        try:
            await message.answer("Faqat PDF yuboring.", reply_markup=kb_cancel())
        except Exception:
            pass
        return
    try:
        file_path = os.path.join(DOWNLOAD_DIR, f"{user_id}_{doc.file_id}.pdf")
        await doc.download(destination_file=file_path)
    except Exception:
        return
    group_id = message.media_group_id or "pdfmerge"
    key = (user_id, str(group_id))
    MEDIA_BUFFER.setdefault(key, []).append(file_path)
    old_task = MEDIA_TASK.get(key)
    if old_task and not old_task.done():
        old_task.cancel()

    async def finalize_pdf_group():
        await asyncio.sleep(1.2)
        paths = MEDIA_BUFFER.pop(key, [])
        MEDIA_TASK.pop(key, None)
        if not paths:
            return
        if len(paths) < 2:
            for p in paths:
                safe_remove(p)
            try:
                await bot.send_message(user_id, "Iltimos, kamida 2 ta PDF yuboring.",
                                       reply_markup=kb_cancel())
            except Exception:
                pass
            return
        try:
            status = await bot.send_message(user_id, "⏳ PDFlar birlashtirilmoqda...")
        except Exception:
            status = None
        out_pdf = os.path.join(DOWNLOAD_DIR, f"merged_{user_id}_{int(time.time())}.pdf")
        try:
            merge_pdfs(paths, out_pdf)
            with open(out_pdf, "rb") as f:
                await bot.send_document(
                    user_id,
                    types.InputFile(f.name, filename=user_pdf_filename(message.from_user)),
                    caption="✅ Tayyor!"
                )
            inc_uses_and_log(user_id, "pdf_merge")
        except Exception:
            pass
        finally:
            for p in paths:
                safe_remove(p)
            safe_remove(out_pdf)
            if status:
                try:
                    await bot.delete_message(user_id, status.message_id)
                except Exception:
                    pass
        await show_main_menu(user_id)

    MEDIA_TASK[key] = asyncio.create_task(finalize_pdf_group())


# ======================
#   STARTUP
# ======================
async def on_startup(_dp: Dispatcher):
    db_init()
    asyncio.create_task(cleanup_worker())


if __name__ == "__main__":
    print("Bot ishga tushdi...")
    executor.start_polling(dp, skip_updates=True, on_startup=on_startup)






