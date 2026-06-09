"""
Chart rendering for admin analytics.
"""
import io
import logging
from typing import Dict

from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)

# Chart configuration
ACTIONS = ["text_pdf", "img_pdf", "upscale", "pdf_merge", "smart_scan", "compress_pdf"]
COLORS = {
    "text_pdf": (59, 130, 246),
    "img_pdf": (16, 185, 129),
    "upscale": (245, 158, 11),
    "pdf_merge": (168, 85, 247),
    "smart_scan": (239, 68, 68),
    "compress_pdf": (34, 197, 94),
}
LABELS = {
    "text_pdf": "Matn→PDF",
    "img_pdf": "Rasm→PDF",
    "upscale": "Upscale",
    "pdf_merge": "PDF merge",
    "smart_scan": "Scan",
    "compress_pdf": "Compress",
}


def _get_font(size: int):
    """Get font, falling back to default if DejaVu not available."""
    font_paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/dejavu/DejaVuSans.ttf",
        "DejaVuSans.ttf",
    ]
    for path in font_paths:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            continue
    return ImageFont.load_default()


def render_usage_chart_png(data: Dict[str, Dict[str, int]],
                           title: str = "So'nggi 7 kun") -> bytes:
    """Render a stacked bar chart as PNG bytes."""
    W, H = 1150, 520
    pad_l, pad_r, pad_t, pad_b = 70, 40, 70, 70

    bg = Image.new("RGB", (W, H), (250, 250, 252))
    d = ImageDraw.Draw(bg)

    font = _get_font(20)
    font_small = _get_font(14)
    font_tiny = _get_font(12)

    d.text((pad_l, 18), title, fill=(20, 20, 25), font=font)

    if not data:
        d.text((pad_l, 110), "Ma'lumot yo'q.", fill=(50, 50, 60), font=font_small)
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
                        radius=18, fill=(255, 255, 255), outline=(230, 230, 235), width=2)

    # Grid lines
    grid_n = 5
    for i in range(grid_n + 1):
        y = y1 - int(plot_h * i / grid_n)
        d.line((x0, y, x1, y), fill=(235, 235, 240), width=1)
        val = int(max_total * i / grid_n)
        d.text((x0 - 48, y - 8), str(val), fill=(120, 120, 130), font=font_tiny)

    # Bars
    n = len(days_list)
    gap = 10
    bar_w = min(max(18, int((plot_w - gap * (n - 1)) / max(n, 1))), 90)
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
            d.rounded_rectangle([x, y_top, x + bar_w, y_base], radius=10, fill=color)
            y_base = y_top
        d.text((x + 4, y_base - 18), str(totals[i]), fill=(40, 40, 45), font=font_tiny)
        day_lbl = day[5:] if len(day) >= 10 else day
        d.text((x, y1 + 10), day_lbl, fill=(90, 90, 100), font=font_tiny)

    # Legend
    lx = x1 - 380
    ly = pad_t - 52
    d.rounded_rectangle([lx, ly, x1, ly + 48], radius=14,
                        fill=(255, 255, 255), outline=(230, 230, 235), width=2)
    cx, cy = lx + 12, ly + 14
    for a in ACTIONS:
        if cx + 60 > x1:
            break
        color = COLORS.get(a, (150, 150, 150))
        d.rectangle([cx, cy, cx + 14, cy + 14], fill=color)
        d.text((cx + 18, cy - 2), LABELS.get(a, a), fill=(40, 40, 45), font=font_tiny)
        cx += 62

    buf = io.BytesIO()
    bg.save(buf, format="PNG")
    return buf.getvalue()
