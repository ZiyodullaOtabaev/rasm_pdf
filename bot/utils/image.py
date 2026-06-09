"""
Image processing utilities: upscale, smart scan.
"""
import os
import logging
import subprocess

import cv2
import numpy as np
from PIL import Image

from bot.config import ENABLE_REAL_AI, REAL_ESRGAN_BIN, REAL_ESRGAN_MODELS

logger = logging.getLogger(__name__)


def pillow_upscale_2x(in_path: str, out_path: str):
    """Upscale image 2x using Pillow LANCZOS."""
    img = Image.open(in_path)
    new_size = (img.width * 2, img.height * 2)
    up = img.resize(new_size, Image.LANCZOS)
    up.save(out_path, quality=95, optimize=True)
    logger.info(f"Pillow upscale 2x: {in_path} -> {out_path}")


def try_realesrgan(in_path: str, out_path: str) -> bool:
    """Try Real-ESRGAN AI upscale. Returns True if successful."""
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
        success = p.returncode == 0 and os.path.exists(out_path)
        if success:
            logger.info(f"Real-ESRGAN upscale success: {in_path}")
        return success
    except Exception as e:
        logger.warning(f"Real-ESRGAN failed: {e}")
        return False


def smart_scan_document(input_path: str, output_path: str):
    """
    Smart document scan: perspective correction + quality enhancement.
    """
    image = cv2.imread(input_path)
    if image is None:
        raise RuntimeError("Image topilmadi yoki o'qib bo'lmadi")

    original = image.copy()

    # Resize for detection
    ratio = image.shape[0] / 1000.0
    resized = cv2.resize(image, (int(image.shape[1] / ratio), 1000))

    gray = cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    edged = cv2.Canny(blur, 50, 150)

    contours, _ = cv2.findContours(edged.copy(), cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    contours = sorted(contours, key=cv2.contourArea, reverse=True)[:10]

    doc_contour = None
    for contour in contours:
        peri = cv2.arcLength(contour, True)
        approx = cv2.approxPolyDP(contour, 0.02 * peri, True)
        if len(approx) == 4:
            doc_contour = approx
            break

    # If document contour not found, use original
    if doc_contour is None:
        cropped = original
    else:
        pts = doc_contour.reshape(4, 2) * ratio
        rect = np.zeros((4, 2), dtype="float32")

        s = pts.sum(axis=1)
        rect[0] = pts[np.argmin(s)]
        rect[2] = pts[np.argmax(s)]

        diff = np.diff(pts, axis=1)
        rect[1] = pts[np.argmin(diff)]
        rect[3] = pts[np.argmax(diff)]

        (tl, tr, br, bl) = rect

        widthA = np.linalg.norm(br - bl)
        widthB = np.linalg.norm(tr - tl)
        maxWidth = max(int(widthA), int(widthB))

        heightA = np.linalg.norm(tr - br)
        heightB = np.linalg.norm(tl - bl)
        maxHeight = max(int(heightA), int(heightB))

        dst = np.array([
            [0, 0],
            [maxWidth - 1, 0],
            [maxWidth - 1, maxHeight - 1],
            [0, maxHeight - 1]
        ], dtype="float32")

        matrix = cv2.getPerspectiveTransform(rect, dst)
        cropped = cv2.warpPerspective(original, matrix, (maxWidth, maxHeight))

    # Quality enhancement
    gray = cv2.cvtColor(cropped, cv2.COLOR_BGR2GRAY)
    denoise = cv2.fastNlMeansDenoising(gray, None, 8, 7, 21)

    clahe = cv2.createCLAHE(clipLimit=2.8, tileGridSize=(8, 8))
    enhanced = clahe.apply(denoise)

    blur = cv2.GaussianBlur(enhanced, (0, 0), 1.5)
    sharp = cv2.addWeighted(enhanced, 1.65, blur, -0.65, 0)

    # Text clarity boost
    kernel = np.array([[-1, -1, -1], [-1, 9, -1], [-1, -1, -1]])
    sharp = cv2.filter2D(sharp, -1, kernel)

    cv2.imwrite(output_path, sharp, [cv2.IMWRITE_JPEG_QUALITY, 95])
    logger.info(f"Smart scan complete: {input_path} -> {output_path}")
