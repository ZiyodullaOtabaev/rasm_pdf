"""
PDF generation, merging, and compression utilities.
"""
import io
import os
import logging
from typing import List

from PIL import Image
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from PyPDF2 import PdfMerger
import fitz

logger = logging.getLogger(__name__)

# Try to register a Unicode-capable font
UNICODE_FONT_NAME = "DejaVuSans"
UNICODE_FONT_REGISTERED = False

# Common paths for DejaVu Sans
_FONT_PATHS = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/TTF/DejaVuSans.ttf",
    "/usr/local/share/fonts/DejaVuSans.ttf",
    "C:/Windows/Fonts/DejaVuSans.ttf",
    "DejaVuSans.ttf",
]

for _path in _FONT_PATHS:
    if os.path.exists(_path):
        try:
            pdfmetrics.registerFont(TTFont(UNICODE_FONT_NAME, _path))
            UNICODE_FONT_REGISTERED = True
            logger.info(f"Registered Unicode font from: {_path}")
            break
        except Exception as e:
            logger.warning(f"Failed to register font {_path}: {e}")

if not UNICODE_FONT_REGISTERED:
    logger.warning("Unicode font not found. PDF text may not render Cyrillic/Uzbek characters correctly.")


def make_text_pdf_bytes(text: str) -> bytes:
    """Convert text to PDF bytes with Unicode support."""
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    width, height = A4
    margin = 50
    y = height - margin
    line_height = 14

    # Use Unicode font if available, fallback to Helvetica
    font_name = UNICODE_FONT_NAME if UNICODE_FONT_REGISTERED else "Helvetica"
    font_size = 11

    def wrap_line(s: str, max_chars: int = 90) -> List[str]:
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

    c.setFont(font_name, font_size)
    for line in lines:
        if y < margin:
            c.showPage()
            c.setFont(font_name, font_size)
            y = height - margin
        c.drawString(margin, y, line)
        y -= line_height

    c.showPage()
    c.save()
    buf.seek(0)
    return buf.read()


def images_to_pdf(path_list: List[str], out_pdf_path: str):
    """Convert a list of images to a single PDF."""
    imgs = []
    for p in path_list:
        try:
            imgs.append(Image.open(p).convert("RGB"))
        except Exception as e:
            logger.error(f"Failed to open image {p}: {e}")

    if not imgs:
        raise RuntimeError("No valid images to convert")

    first, rest = imgs[0], imgs[1:]
    first.save(out_pdf_path, save_all=True, append_images=rest)
    logger.info(f"Created PDF from {len(imgs)} images: {out_pdf_path}")


def merge_pdfs(pdf_paths: List[str], out_pdf_path: str):
    """Merge multiple PDF files into one."""
    merger = PdfMerger()
    try:
        for p in pdf_paths:
            merger.append(p)
        with open(out_pdf_path, "wb") as f:
            merger.write(f)
        logger.info(f"Merged {len(pdf_paths)} PDFs into: {out_pdf_path}")
    finally:
        try:
            merger.close()
        except Exception:
            pass


def compress_pdf(input_path: str, output_path: str) -> dict:
    """
    Smart PDF compression that preserves visual quality.
    
    Strategy:
    - Large images (>1500px) are downscaled to reasonable dimensions
    - JPEG quality kept at 82 (visually lossless for most content)
    - Small images are left untouched
    - PDF structure is optimized (garbage collection, deflate)
    
    Returns dict with stats: {old_size, new_size, images_processed}
    """
    if not os.path.exists(input_path):
        raise FileNotFoundError("PDF topilmadi")

    doc = fitz.open(input_path)

    try:
        if doc.needs_pass:
            raise RuntimeError("Parolli PDF siqilmaydi")

        images_processed = 0

        for page in doc:
            img_list = page.get_images(full=True)

            for img in img_list:
                xref = img[0]
                try:
                    base_image = doc.extract_image(xref)
                    image_bytes = base_image["image"]
                    img_ext = base_image.get("ext", "png")
                    img_width = base_image.get("width", 0)
                    img_height = base_image.get("height", 0)

                    # Skip very small images (icons, logos) — don't compress
                    if img_width < 100 or img_height < 100:
                        continue

                    # Skip if image is already small in file size (<50KB)
                    if len(image_bytes) < 50 * 1024:
                        continue

                    # Open with Pillow for quality-preserving compression
                    pil_img = Image.open(io.BytesIO(image_bytes))

                    # Downscale large images (>2000px on any side)
                    max_dimension = 1600
                    if img_width > max_dimension or img_height > max_dimension:
                        ratio = min(max_dimension / img_width, max_dimension / img_height)
                        new_w = int(img_width * ratio)
                        new_h = int(img_height * ratio)
                        pil_img = pil_img.resize((new_w, new_h), Image.LANCZOS)

                    # Convert to RGB if needed (for JPEG encoding)
                    if pil_img.mode in ("RGBA", "P"):
                        # If has transparency, use PNG with compression
                        buf = io.BytesIO()
                        pil_img.save(buf, format="PNG", optimize=True)
                        buf.seek(0)
                        new_bytes = buf.read()
                    else:
                        # Use JPEG with good quality
                        if pil_img.mode != "RGB":
                            pil_img = pil_img.convert("RGB")
                        buf = io.BytesIO()
                        pil_img.save(buf, format="JPEG", quality=82, optimize=True)
                        buf.seek(0)
                        new_bytes = buf.read()

                    # Only use compressed version if it's actually smaller
                    if len(new_bytes) < len(image_bytes):
                        doc.update_stream(xref, new_bytes)
                        images_processed += 1

                except Exception as e:
                    logger.debug(f"Skipping image xref={xref}: {e}")
                    continue

        # Save with structure optimization
        doc.save(
            output_path,
            garbage=4,      # Remove unused objects
            deflate=True,   # Compress streams
            clean=True,     # Clean up redundant info
            linear=True,    # Optimize for web viewing
        )
    finally:
        doc.close()

    if not os.path.exists(output_path):
        raise RuntimeError("PDF siqilmadi")

    old_size = os.path.getsize(input_path)
    new_size = os.path.getsize(output_path)
    logger.info(f"Compressed PDF: {input_path} -> {output_path} "
                f"({old_size//1024}KB -> {new_size//1024}KB, "
                f"{images_processed} images processed)")

    return {
        "old_size": old_size,
        "new_size": new_size,
        "images_processed": images_processed,
    }
