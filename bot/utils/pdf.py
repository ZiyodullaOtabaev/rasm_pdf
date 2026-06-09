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
import cv2
import numpy as np

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


def compress_pdf(input_path: str, output_path: str):
    """Compress a PDF file by recompressing images."""
    if not os.path.exists(input_path):
        raise FileNotFoundError("PDF topilmadi")

    doc = fitz.open(input_path)

    try:
        if doc.needs_pass:
            raise RuntimeError("Parolli PDF siqilmaydi")

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

                    _, compressed = cv2.imencode(
                        ".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 60]
                    )
                    doc.update_stream(xref, compressed.tobytes())
                except Exception as e:
                    logger.debug(f"Skipping image xref={xref}: {e}")
                    continue

        doc.save(output_path, garbage=4, deflate=True, clean=True)
    finally:
        doc.close()

    if not os.path.exists(output_path):
        raise RuntimeError("PDF siqilmadi")

    logger.info(f"Compressed PDF: {input_path} -> {output_path}")
