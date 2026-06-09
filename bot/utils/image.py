"""
Image processing utilities: upscale, smart scan.
"""
import os
import logging
import subprocess

import cv2
import numpy as np
from PIL import Image, ImageEnhance, ImageFilter

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
    Professional document scan:
    1. Detect document edges (perspective correction)
    2. Light color enhancement (preserve readability)
    3. Keep COLOR output (not grayscale!)
    4. Subtle sharpening for text clarity
    
    Result: clean, bright, readable document photo — similar to CamScanner/Adobe Scan.
    """
    image = cv2.imread(input_path)
    if image is None:
        raise RuntimeError("Image topilmadi yoki o'qib bo'lmadi")

    original = image.copy()

    # === STEP 1: Document edge detection & perspective correction ===
    cropped = _detect_and_crop_document(original)

    # === STEP 2: Color enhancement (keep it in COLOR, not grayscale!) ===
    result = _enhance_document_color(cropped)

    # Save with high quality
    cv2.imwrite(output_path, result, [cv2.IMWRITE_JPEG_QUALITY, 95])
    logger.info(f"Smart scan complete: {input_path} -> {output_path}")


def _detect_and_crop_document(image: np.ndarray) -> np.ndarray:
    """
    Detect document boundaries and apply perspective transform.
    If no clear document found, returns original image.
    """
    h, w = image.shape[:2]

    # Resize for faster edge detection
    scale = 800.0 / max(h, w)
    if scale < 1.0:
        resized = cv2.resize(image, None, fx=scale, fy=scale)
    else:
        resized = image.copy()
        scale = 1.0

    # Convert to grayscale and blur
    gray = cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (7, 7), 0)

    # Adaptive thresholding for better edge detection
    # Try multiple approaches
    edged = cv2.Canny(blur, 30, 120)

    # Dilate to close gaps
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    edged = cv2.dilate(edged, kernel, iterations=1)

    # Find contours
    contours, _ = cv2.findContours(edged, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    if not contours:
        return image

    # Sort by area, take top candidates
    contours = sorted(contours, key=cv2.contourArea, reverse=True)[:5]

    doc_contour = None
    min_area = (resized.shape[0] * resized.shape[1]) * 0.2  # At least 20% of image

    for contour in contours:
        area = cv2.contourArea(contour)
        if area < min_area:
            continue

        peri = cv2.arcLength(contour, True)
        approx = cv2.approxPolyDP(contour, 0.02 * peri, True)

        if len(approx) == 4:
            doc_contour = approx
            break

    if doc_contour is None:
        return image

    # Scale points back to original size
    pts = doc_contour.reshape(4, 2) / scale

    # Order points: top-left, top-right, bottom-right, bottom-left
    rect = _order_points(pts)
    (tl, tr, br, bl) = rect

    # Calculate new dimensions
    widthA = np.linalg.norm(br - bl)
    widthB = np.linalg.norm(tr - tl)
    maxWidth = max(int(widthA), int(widthB))

    heightA = np.linalg.norm(tr - br)
    heightB = np.linalg.norm(tl - bl)
    maxHeight = max(int(heightA), int(heightB))

    # Perspective transform
    dst = np.array([
        [0, 0],
        [maxWidth - 1, 0],
        [maxWidth - 1, maxHeight - 1],
        [0, maxHeight - 1]
    ], dtype="float32")

    matrix = cv2.getPerspectiveTransform(rect, dst)
    warped = cv2.warpPerspective(image, matrix, (maxWidth, maxHeight))

    return warped


def _order_points(pts: np.ndarray) -> np.ndarray:
    """Order 4 points as: top-left, top-right, bottom-right, bottom-left."""
    rect = np.zeros((4, 2), dtype="float32")

    s = pts.sum(axis=1)
    rect[0] = pts[np.argmin(s)]   # top-left: smallest sum
    rect[2] = pts[np.argmax(s)]   # bottom-right: largest sum

    diff = np.diff(pts, axis=1)
    rect[1] = pts[np.argmin(diff)]  # top-right: smallest diff
    rect[3] = pts[np.argmax(diff)]  # bottom-left: largest diff

    return rect


def _enhance_document_color(image: np.ndarray) -> np.ndarray:
    """
    Enhance document photo while keeping natural colors.
    Makes background whiter and text/content more readable.
    """
    # Convert to LAB color space for better processing
    lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)
    l_channel, a_channel, b_channel = cv2.split(lab)

    # === Lightness enhancement ===
    # Use CLAHE only on L channel with mild settings
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    l_enhanced = clahe.apply(l_channel)

    # Make background brighter (push light areas toward white)
    # This simulates scanner white-background effect
    l_float = l_enhanced.astype(np.float32)
    # Gamma correction to brighten light areas more
    l_float = np.power(l_float / 255.0, 0.85) * 255.0
    l_enhanced = np.clip(l_float, 0, 255).astype(np.uint8)

    # Merge back
    enhanced_lab = cv2.merge([l_enhanced, a_channel, b_channel])
    enhanced = cv2.cvtColor(enhanced_lab, cv2.COLOR_LAB2BGR)

    # === Subtle sharpening (not aggressive!) ===
    # Unsharp mask with mild parameters
    gaussian = cv2.GaussianBlur(enhanced, (0, 0), 2.0)
    sharpened = cv2.addWeighted(enhanced, 1.3, gaussian, -0.3, 0)

    # === Slight saturation boost for natural look ===
    hsv = cv2.cvtColor(sharpened, cv2.COLOR_BGR2HSV)
    h, s, v = cv2.split(hsv)
    s = cv2.add(s, 10)  # Very subtle saturation boost
    final_hsv = cv2.merge([h, s, v])
    result = cv2.cvtColor(final_hsv, cv2.COLOR_HSV2BGR)

    return result
