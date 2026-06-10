"""
Chart rendering for admin analytics — all stats as images.
"""
import io
import logging
from typing import Dict, List, Tuple

from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)

# Colors
ACTIONS = ["text_pdf", "img_pdf", "upscale", "pdf_merge"]
COLORS = {
    "text_pdf": (59, 130, 246),
    "img_pdf": (16, 185, 129),
    "upscale": (245, 158, 11),
    "pdf_merge": (168, 85, 247),
}
LABELS = {
    "text_pdf": "Matn->PDF",
    "img_pdf": "Rasm->PDF",
    "upscale": "Upscale",
    "pdf_merge": "PDF merge",
}


def _get_font(size: int):
    """Get font, falling back to default if not available."""
    font_paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/dejavu/DejaVuSans.ttf",
        "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/segoeui.ttf",
        "C:/Windows/Fonts/tahoma.ttf",
        "DejaVuSans.ttf",
    ]
    for path in font_paths:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            continue
    return ImageFont.load_default()


def render_stats_image(stats: dict, action_stats: Dict[str, int]) -> bytes:
    """
    Render full statistics dashboard as a single PNG image.
    Shows: user counts, activity, action breakdown.
    """
    W, H = 800, 520
    bg = Image.new("RGB", (W, H), (22, 27, 34))
    d = ImageDraw.Draw(bg)

    font_title = _get_font(22)
    font_big = _get_font(28)
    font_med = _get_font(16)
    font_small = _get_font(13)

    # Title
    d.text((30, 20), "📊 Bot Statistikasi", fill=(255, 255, 255), font=font_title)
    d.line((30, 55, W - 30, 55), fill=(50, 60, 75), width=1)

    # === ROW 1: Main stats cards ===
    cards = [
        ("👥 Jami", str(stats.get("total_users", 0)), (59, 130, 246)),
        ("⚡ Bugun", str(stats.get("uses_today", 0)), (16, 185, 129)),
        ("📅 Hafta", str(stats.get("uses_week", 0)), (245, 158, 11)),
        ("🆕 Yangi 24h", str(stats.get("new_24h", 0)), (236, 72, 153)),
    ]

    card_w = (W - 80) // 4
    for i, (label, value, color) in enumerate(cards):
        x = 30 + i * (card_w + 12)
        y = 70
        # Card background
        d.rounded_rectangle([x, y, x + card_w, y + 90], radius=12, fill=(30, 37, 46))
        d.rounded_rectangle([x, y, x + card_w, y + 4], radius=2, fill=color)
        # Value
        d.text((x + 15, y + 20), value, fill=(255, 255, 255), font=font_big)
        # Label
        d.text((x + 15, y + 60), label, fill=(160, 170, 185), font=font_small)

    # === ROW 2: More stats ===
    y2 = 180
    cards2 = [
        ("🟢 Aktiv 24h", str(stats.get("active_24h", 0))),
        ("📅 Aktiv 7kun", str(stats.get("active_7d", 0))),
        ("🆕 Yangi 7kun", str(stats.get("new_7d", 0))),
        ("📊 Jami amal", str(stats.get("total_uses", 0))),
    ]

    for i, (label, value) in enumerate(cards2):
        x = 30 + i * (card_w + 12)
        d.rounded_rectangle([x, y2, x + card_w, y2 + 70], radius=10, fill=(30, 37, 46))
        d.text((x + 15, y2 + 12), value, fill=(255, 255, 255), font=font_med)
        d.text((x + 15, y2 + 40), label, fill=(140, 150, 165), font=font_small)

    # === ROW 3: Action breakdown with bars ===
    y3 = 280
    d.text((30, y3), "📋 Funksiyalar:", fill=(200, 210, 220), font=font_med)
    y3 += 30

    total_actions = sum(action_stats.values()) or 1
    action_names = {
        "text_pdf": "📝 Matn -> PDF",
        "img_pdf": "🖼 Rasm -> PDF",
        "upscale": "✨ Sifat oshirish",
        "pdf_merge": "📎 PDF merge",
    }

    bar_max_w = W - 200
    for action in ACTIONS:
        count = action_stats.get(action, 0)
        pct = count / total_actions * 100
        bar_w = int(bar_max_w * count / max(max(action_stats.values(), default=1), 1))
        color = COLORS.get(action, (100, 100, 100))
        name = action_names.get(action, action)

        # Bar background
        d.rounded_rectangle([160, y3 + 2, 160 + bar_max_w, y3 + 28], radius=6, fill=(40, 48, 58))
        # Bar fill
        if bar_w > 0:
            d.rounded_rectangle([160, y3 + 2, 160 + max(bar_w, 8), y3 + 28], radius=6, fill=color)
        # Label
        d.text((30, y3 + 5), name, fill=(180, 190, 200), font=font_small)
        # Count
        d.text((160 + bar_max_w + 10, y3 + 5), f"{count} ({pct:.0f}%)",
               fill=(160, 170, 180), font=font_small)
        y3 += 40

    # Footer
    d.line((30, H - 40, W - 30, H - 40), fill=(40, 50, 60), width=1)
    d.text((30, H - 30), "Rasm PDF Bot | Admin Panel",
           fill=(80, 90, 100), font=font_small)

    buf = io.BytesIO()
    bg.save(buf, format="PNG")
    return buf.getvalue()


def render_usage_chart_png(data: Dict[str, Dict[str, int]],
                           title: str = "So'nggi 7 kun") -> bytes:
    """Render a stacked bar chart as PNG bytes."""
    W, H = 1000, 450
    pad_l, pad_r, pad_t, pad_b = 70, 40, 60, 60

    bg = Image.new("RGB", (W, H), (22, 27, 34))
    d = ImageDraw.Draw(bg)

    font = _get_font(18)
    font_tiny = _get_font(11)

    d.text((pad_l, 15), title, fill=(220, 230, 240), font=font)

    if not data:
        d.text((pad_l, 100), "Ma'lumot yo'q.", fill=(150, 150, 160), font=font)
        buf = io.BytesIO()
        bg.save(buf, format="PNG")
        return buf.getvalue()

    days_list = list(data.keys())

    totals = []
    max_total = 0
    for day in days_list:
        t = sum(data.get(day, {}).get(a, 0) for a in ACTIONS)
        totals.append(t)
        max_total = max(max_total, t)
    max_total = max_total or 1

    x0, y0 = pad_l, pad_t
    x1, y1 = W - pad_r, H - pad_b
    plot_w = x1 - x0
    plot_h = y1 - y0

    d.rounded_rectangle([x0 - 10, y0 - 10, x1 + 10, y1 + 10],
                        radius=14, fill=(30, 37, 46), outline=(50, 60, 75), width=1)

    # Grid lines
    grid_n = 5
    for i in range(grid_n + 1):
        y = y1 - int(plot_h * i / grid_n)
        d.line((x0, y, x1, y), fill=(45, 55, 68), width=1)
        val = int(max_total * i / grid_n)
        d.text((x0 - 40, y - 7), str(val), fill=(120, 130, 145), font=font_tiny)

    # Bars
    n = len(days_list)
    gap = 10
    bar_w = min(max(20, int((plot_w - gap * (n - 1)) / max(n, 1))), 80)
    total_bars_w = bar_w * n + gap * (n - 1)
    start_x = x0 + max(0, (plot_w - total_bars_w) // 2)

    for i, day in enumerate(days_list):
        x = start_x + i * (bar_w + gap)
        y_base = y1
        for a in ACTIONS:
            v = data.get(day, {}).get(a, 0)
            if v <= 0:
                continue
            h = int(plot_h * (v / max_total))
            y_top = y_base - h
            color = COLORS.get(a, (150, 150, 150))
            d.rounded_rectangle([x, y_top, x + bar_w, y_base], radius=8, fill=color)
            y_base = y_top
        # Total on top
        if totals[i] > 0:
            d.text((x + 4, y_base - 16), str(totals[i]), fill=(200, 210, 220), font=font_tiny)
        # Date label
        day_lbl = day[5:] if len(day) >= 10 else day
        d.text((x, y1 + 8), day_lbl, fill=(120, 130, 145), font=font_tiny)

    # Legend
    lx = x1 - 280
    ly = 15
    cx = lx
    for a in ACTIONS:
        color = COLORS.get(a, (150, 150, 150))
        d.rectangle([cx, ly + 4, cx + 12, ly + 16], fill=color)
        d.text((cx + 16, ly + 2), LABELS.get(a, a), fill=(180, 190, 200), font=font_tiny)
        cx += 70

    buf = io.BytesIO()
    bg.save(buf, format="PNG")
    return buf.getvalue()


def render_growth_chart_png(data: List[Tuple[str, int]],
                            title: str = "Yangi foydalanuvchilar") -> bytes:
    """Render a line chart of user growth."""
    W, H = 900, 380
    pad_l, pad_r, pad_t, pad_b = 60, 40, 55, 55

    bg = Image.new("RGB", (W, H), (22, 27, 34))
    d = ImageDraw.Draw(bg)

    font = _get_font(16)
    font_tiny = _get_font(10)

    d.text((pad_l, 15), title, fill=(220, 230, 240), font=font)

    if not data:
        d.text((pad_l, 100), "Ma'lumot yo'q.", fill=(150, 150, 160), font=font)
        buf = io.BytesIO()
        bg.save(buf, format="PNG")
        return buf.getvalue()

    x0, y0 = pad_l, pad_t
    x1, y1 = W - pad_r, H - pad_b
    plot_w = x1 - x0
    plot_h = y1 - y0

    d.rounded_rectangle([x0 - 8, y0 - 8, x1 + 8, y1 + 8],
                        radius=12, fill=(30, 37, 46), outline=(50, 60, 75), width=1)

    values = [v for _, v in data]
    max_val = max(values) if values else 1
    max_val = max_val or 1

    n = len(data)
    if n < 2:
        d.text((pad_l, 100), "Kam ma'lumot.", fill=(150, 150, 160), font=font)
        buf = io.BytesIO()
        bg.save(buf, format="PNG")
        return buf.getvalue()

    # Grid
    for i in range(5):
        y = y1 - int(plot_h * i / 4)
        d.line((x0, y, x1, y), fill=(40, 50, 62), width=1)
        d.text((x0 - 35, y - 6), str(int(max_val * i / 4)), fill=(110, 120, 135), font=font_tiny)

    # Points
    step_x = plot_w / max(n - 1, 1)
    points = []
    for i, (day, val) in enumerate(data):
        px = x0 + int(i * step_x)
        py = y1 - int(plot_h * val / max_val)
        points.append((px, py))

    # Fill area under line
    if len(points) >= 2:
        polygon = points + [(points[-1][0], y1), (points[0][0], y1)]
        d.polygon(polygon, fill=(59, 130, 246, 25))

    # Draw line
    for i in range(len(points) - 1):
        d.line([points[i], points[i + 1]], fill=(59, 130, 246), width=3)

    # Dots + values
    for i, ((day, val), (px, py)) in enumerate(zip(data, points)):
        d.ellipse([px - 4, py - 4, px + 4, py + 4], fill=(59, 130, 246))
        if val > 0:
            d.text((px - 5, py - 15), str(val), fill=(180, 200, 220), font=font_tiny)
        # X labels
        if i % max(1, n // 7) == 0 or i == n - 1:
            lbl = day[5:] if len(day) >= 10 else day
            d.text((px - 10, y1 + 8), lbl, fill=(110, 120, 135), font=font_tiny)

    buf = io.BytesIO()
    bg.save(buf, format="PNG")
    return buf.getvalue()
