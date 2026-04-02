"""
screen_reader.py  —  Capture screen, preprocess aggressively, run OCR,
                     then optionally clean up via LLM.
"""

import os
from datetime import datetime

try:
    from PIL import ImageGrab, Image, ImageEnhance, ImageOps, ImageFilter
    _PIL_OK = True
except ImportError:
    _PIL_OK = False

try:
    import pytesseract
    _TESSERACT_PATHS = [
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
    ]
    if not pytesseract.pytesseract.tesseract_cmd or \
       not os.path.exists(pytesseract.pytesseract.tesseract_cmd):
        for _p in _TESSERACT_PATHS:
            if os.path.exists(_p):
                pytesseract.pytesseract.tesseract_cmd = _p
                break
    _TESS_OK = True
except ImportError:
    _TESS_OK = False

_last_text: str = ""


# ── dependency check ──────────────────────────────────────────────────────────

def _check_deps():
    if not _PIL_OK:
        return "Pillow not installed. Run: pip install pillow"
    if not _TESS_OK:
        return "pytesseract not installed. Run: pip install pytesseract"
    try:
        pytesseract.get_tesseract_version()
    except Exception:
        return (
            "Tesseract OCR binary not found.\n"
            r"Install from: https://github.com/UB-Mannheim/tesseract/wiki"
        )
    return None


# ── capture ───────────────────────────────────────────────────────────────────

def _capture(region=None):
    if region:
        left, top, width, height = region
        return ImageGrab.grab(bbox=(left, top, left+width, top+height), all_screens=True)
    return ImageGrab.grab(all_screens=True)


# ── preprocessing ─────────────────────────────────────────────────────────────

def _make_variants(image):
    """
    Generate multiple image variants optimised for OCR.
    Dark UIs need inversion. Small text needs upscaling.
    """
    w, h = image.size
    # Scale to at least 2400px wide for good Tesseract accuracy
    scale = max(2, int(2400 / w))
    big   = image.resize((w * scale, h * scale), Image.LANCZOS)

    rgb = big.convert("RGB")
    gray = big.convert("L")

    variants = []

    # 1. Plain grayscale upscaled
    variants.append(("plain_gray", gray))

    # 2. Inverted grayscale — best for dark backgrounds (white text → black text)
    inv_gray = ImageOps.invert(gray)
    variants.append(("inv_gray", inv_gray))

    # 3. High contrast inverted — sharpen edges on dark UIs
    inv_contrast = ImageEnhance.Contrast(inv_gray).enhance(3.5)
    inv_sharp    = ImageEnhance.Sharpness(inv_contrast).enhance(3.0)
    variants.append(("inv_contrast", inv_sharp))

    # 4. Thresholded — convert to pure black/white (best for clean text)
    threshold = gray.point(lambda p: 255 if p > 128 else 0, '1')
    variants.append(("threshold_normal", threshold))

    inv_threshold = inv_gray.point(lambda p: 255 if p > 100 else 0, '1')
    variants.append(("threshold_inv", inv_threshold))

    # 5. Denoised inverted — helps with UI artefacts
    denoised = inv_contrast.filter(ImageFilter.MedianFilter(size=3))
    variants.append(("denoised", denoised))

    return variants


# ── OCR ───────────────────────────────────────────────────────────────────────

def _run_ocr(variants) -> str:
    """Run Tesseract on every variant, return the richest result."""
    configs = [
        "--oem 3 --psm 6",   # uniform block of text
        "--oem 3 --psm 4",   # single column
        "--oem 3 --psm 11",  # sparse text — good for UI elements
    ]

    best = ""
    for name, img in variants:
        for cfg in configs:
            try:
                text = pytesseract.image_to_string(img, lang="eng", config=cfg).strip()
                if len(text.replace(" ","").replace("\n","")) > \
                   len(best.replace(" ","").replace("\n","")):
                    best = text
            except Exception:
                continue
    return best


# ── LLM cleanup ───────────────────────────────────────────────────────────────

def _llm_clean(raw: str) -> str:
    """
    Send raw OCR output to the local LLM to correct garbled text.
    Falls back to raw text if LLM is unavailable.
    """
    if not raw or len(raw.strip()) < 10:
        return raw

    try:
        import ollama
        from settings import get_setting

        model = get_setting("model") or "qwen2.5:3b"

        prompt = (
            "The following is raw OCR text extracted from a computer screen. "
            "It may contain garbled characters, split words, or OCR errors. "
            "Please clean it up into readable text, preserving all actual content. "
            "Only output the corrected text, nothing else.\n\n"
            f"RAW OCR:\n{raw}"
        )

        response = ollama.chat(
            model=model,
            messages=[{"role": "user", "content": prompt}]
        )

        cleaned = response["message"]["content"].strip()
        return cleaned if cleaned else raw

    except Exception:
        return raw


# ── text cleanup ──────────────────────────────────────────────────────────────

def _clean(text: str) -> str:
    """Remove excessive blank lines."""
    lines = text.splitlines()
    out, prev_blank = [], False
    for line in lines:
        blank = not line.strip()
        if blank and prev_blank:
            continue
        out.append(line)
        prev_blank = blank
    return "\n".join(out).strip()


# ── screenshots folder ────────────────────────────────────────────────────────

def _screenshots_dir() -> str:
    try:
        from settings import resource_path
        path = resource_path("screenshots")
    except Exception:
        path = os.path.join(os.path.dirname(__file__), "screenshots")
    os.makedirs(path, exist_ok=True)
    return path


# ── public API ────────────────────────────────────────────────────────────────

def read_screen(region=None, llm_clean=True) -> str:
    """
    Capture screen, run OCR, optionally clean via LLM.

    Parameters
    ----------
    region    : (left, top, width, height) or None for full screen
    llm_clean : bool — pass OCR output through LLM to fix garbled text
    """
    global _last_text

    err = _check_deps()
    if err:
        return err

    try:
        image    = _capture(region)
        variants = _make_variants(image)
        raw      = _run_ocr(variants)
        raw      = _clean(raw)

        if not raw:
            return "Screen captured but no text was detected."

        # LLM cleanup pass
        if llm_clean:
            text = _llm_clean(raw)
        else:
            text = raw

        text = _clean(text)
        _last_text = text
        return text

    except Exception as e:
        return f"Screen read failed: {e}"


def read_screen_region(left: int, top: int, width: int, height: int) -> str:
    """Read text from a specific screen region."""
    return read_screen(region=(left, top, width, height))


def read_screen_raw(region=None) -> str:
    """Return raw OCR output without LLM cleanup."""
    return read_screen(region=region, llm_clean=False)


def screenshot_to_file(path: str = None) -> str:
    """Save a screenshot and return the file path."""
    err = _check_deps()
    if err:
        return err
    try:
        if path is None:
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            path  = os.path.join(_screenshots_dir(), f"screen_{stamp}.png")
        image = _capture()
        image.save(path)
        return path
    except Exception as e:
        return f"Screenshot failed: {e}"


def last_screen_text() -> str:
    """Return the most recently read screen text."""
    if not _last_text:
        return "No screen has been read yet this session."
    return _last_text
