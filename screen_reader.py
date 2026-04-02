"""
screen_reader.py  —  Screen capture, OCR, handwriting correction, and
                     LLM-powered screen explanation.

New public API (additions over original):
  read_handwriting(path)          – OCR an image/scan, then LLM-correct it
  explain_screen(region=None)     – Describe what is on screen using vision LLM
  explain_screen_region(...)      – Explain a specific region
"""

import os
import base64
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
        return ImageGrab.grab(bbox=(left, top, left + width, top + height), all_screens=True)
    return ImageGrab.grab(all_screens=True)


# ── preprocessing ─────────────────────────────────────────────────────────────

def _make_variants(image):
    """Generate multiple image variants optimised for OCR."""
    w, h = image.size
    scale = max(2, int(2400 / w))
    big   = image.resize((w * scale, h * scale), Image.LANCZOS)

    gray = big.convert("L")

    variants = []
    variants.append(("plain_gray", gray))

    inv_gray = ImageOps.invert(gray)
    variants.append(("inv_gray", inv_gray))

    inv_contrast = ImageEnhance.Contrast(inv_gray).enhance(3.5)
    inv_sharp    = ImageEnhance.Sharpness(inv_contrast).enhance(3.0)
    variants.append(("inv_contrast", inv_sharp))

    threshold = gray.point(lambda p: 255 if p > 128 else 0, '1')
    variants.append(("threshold_normal", threshold))

    inv_threshold = inv_gray.point(lambda p: 255 if p > 100 else 0, '1')
    variants.append(("threshold_inv", inv_threshold))

    denoised = inv_contrast.filter(ImageFilter.MedianFilter(size=3))
    variants.append(("denoised", denoised))

    return variants


def _make_handwriting_variants(image):
    """
    Extra preprocessing variants tuned for handwritten text.
    Handwriting benefits from stronger contrast and larger upscaling.
    """
    w, h = image.size
    scale = max(3, int(3000 / w))   # larger scale for handwriting
    big   = image.resize((w * scale, h * scale), Image.LANCZOS)

    gray = big.convert("L")
    variants = []

    # Strong contrast boost
    contrast = ImageEnhance.Contrast(gray).enhance(4.0)
    sharp    = ImageEnhance.Sharpness(contrast).enhance(4.0)
    variants.append(("hw_contrast", sharp))

    # Adaptive-like threshold — good for uneven ink
    adaptive = gray.point(lambda p: 255 if p > 160 else 0, '1')
    variants.append(("hw_threshold_light", adaptive))

    adaptive_dark = gray.point(lambda p: 255 if p > 100 else 0, '1')
    variants.append(("hw_threshold_dark", adaptive_dark))

    inv_gray     = ImageOps.invert(gray)
    inv_contrast = ImageEnhance.Contrast(inv_gray).enhance(4.0)
    variants.append(("hw_inv_contrast", inv_contrast))

    denoised = sharp.filter(ImageFilter.MedianFilter(size=3))
    variants.append(("hw_denoised", denoised))

    return variants


# ── OCR ───────────────────────────────────────────────────────────────────────

def _run_ocr(variants, handwriting=False) -> str:
    """Run Tesseract on every variant, return the richest result."""
    configs = [
        "--oem 3 --psm 6",
        "--oem 3 --psm 4",
        "--oem 3 --psm 11",
    ]

    if handwriting:
        # LSTM engine is better for cursive / handwriting
        configs += [
            "--oem 1 --psm 6",
            "--oem 1 --psm 13",
        ]

    best = ""
    for name, img in variants:
        for cfg in configs:
            try:
                text = pytesseract.image_to_string(img, lang="eng", config=cfg).strip()
                if len(text.replace(" ", "").replace("\n", "")) > \
                   len(best.replace(" ", "").replace("\n", "")):
                    best = text
            except Exception:
                continue
    return best


# ── image → base64 ────────────────────────────────────────────────────────────

def _image_to_base64(image, fmt="PNG") -> str:
    """Convert a PIL image to a base64 string for vision models."""
    import io
    buf = io.BytesIO()
    image.save(buf, format=fmt)
    return base64.b64encode(buf.getvalue()).decode("utf-8")


# ── LLM cleanup ───────────────────────────────────────────────────────────────

def _llm_clean(raw: str) -> str:
    """Send raw OCR output to the LLM to correct garbled text."""
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


def _llm_correct_handwriting(raw: str, context_hint: str = "") -> str:
    """
    Use the LLM to reconstruct handwritten OCR output.
    More aggressive correction than _llm_clean — handles missing words,
    merged characters, and ambiguous letters common in cursive text.
    """
    if not raw or len(raw.strip()) < 5:
        return raw

    try:
        import ollama
        from settings import get_setting

        model = get_setting("model") or "qwen2.5:3b"

        context_line = (
            f"\nAdditional context about the document: {context_hint}"
            if context_hint else ""
        )

        prompt = (
            "The following text was extracted by OCR from a handwritten document or book scan. "
            "It likely contains many errors: merged letters, wrong characters (e.g. '0' vs 'O', "
            "'1' vs 'l' vs 'I'), missing spaces, garbled words, or random symbols from ink bleed.\n\n"
            "Your task:\n"
            "1. Reconstruct the original handwritten text as accurately as possible.\n"
            "2. Fix all OCR errors while preserving the original meaning and wording.\n"
            "3. Keep the same paragraph and line structure.\n"
            "4. If a word is completely unreadable, write [unclear] in its place.\n"
            "5. Output ONLY the corrected text — no explanations, no preamble.\n"
            f"{context_line}\n\n"
            f"RAW OCR OUTPUT:\n{raw}"
        )

        response = ollama.chat(
            model=model,
            messages=[{"role": "user", "content": prompt}]
        )

        result = response["message"]["content"].strip()
        return result if result else raw

    except Exception:
        return raw


# ── Vision-based screen explanation ──────────────────────────────────────────

def _explain_with_vision(image, prompt_text: str) -> str:
    """
    Send the image to a vision-capable Ollama model for description.
    Falls back to OCR-based explanation if no vision model is available.
    """
    try:
        import ollama
        from settings import get_setting

        VISION_MODELS = [
            "llava:7b",
            "llava:13b",
            "llava-llama3",
            "moondream",
            "bakllava",
        ]

        available_models = [m["name"] for m in ollama.list()["models"]]

        vision_model = None
        for vm in VISION_MODELS:
            for am in available_models:
                if vm.split(":")[0] in am:
                    vision_model = am
                    break
            if vision_model:
                break

        if vision_model is None:
            # Graceful fallback — use OCR text + LLM explanation
            return _explain_via_ocr_fallback(image, prompt_text)

        b64 = _image_to_base64(image)

        response = ollama.chat(
            model=vision_model,
            messages=[
                {
                    "role": "user",
                    "content": prompt_text,
                    "images": [b64],
                }
            ]
        )

        return response["message"]["content"].strip()

    except Exception as e:
        return f"Vision explanation failed: {e}"


def _explain_via_ocr_fallback(image, user_question: str) -> str:
    """
    When no vision model is available, OCR the screen and ask the LLM
    to describe what it contains based on the extracted text.
    """
    try:
        variants = _make_variants(image)
        raw      = _run_ocr(variants)
        raw      = _clean(raw)

        if not raw:
            return "No readable content found on screen to explain."

        import ollama
        from settings import get_setting

        model = get_setting("model") or "qwen2.5:3b"

        prompt = (
            "The following text was extracted from a computer screen via OCR. "
            "Based on this content, please answer the user's question about what is on the screen. "
            "Be specific and helpful to a user who cannot see the screen.\n\n"
            f"SCREEN TEXT:\n{raw}\n\n"
            f"USER QUESTION: {user_question}"
        )

        response = ollama.chat(
            model=model,
            messages=[{"role": "user", "content": prompt}]
        )

        return response["message"]["content"].strip()

    except Exception as e:
        return f"Could not explain screen: {e}"


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


# ══════════════════════════════════════════════════════════════════════════════
#  PUBLIC API — original functions (unchanged behaviour)
# ══════════════════════════════════════════════════════════════════════════════

def read_screen(region=None, llm_clean=True) -> str:
    """
    Capture screen, run OCR, optionally clean via LLM.
    region : (left, top, width, height) or None for full screen
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

        text = _llm_clean(raw) if llm_clean else raw
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


# ══════════════════════════════════════════════════════════════════════════════
#  PUBLIC API — NEW functions
# ══════════════════════════════════════════════════════════════════════════════

def read_handwriting(image_path: str, context_hint: str = "") -> str:
    """
    Read and correct handwritten text from an image file or book scan.

    Uses aggressive OCR preprocessing tuned for handwriting, followed by
    LLM correction to reconstruct garbled or missed characters.

    Parameters
    ----------
    image_path   : path to the image file (jpg, png, tiff, etc.)
    context_hint : optional hint to help the LLM  e.g. "19th century letter"

    Returns
    -------
    Corrected text string.
    """
    err = _check_deps()
    if err:
        return err

    if not os.path.exists(image_path):
        return f"File not found: {image_path}"

    try:
        image    = Image.open(image_path).convert("RGB")
        variants = _make_variants(image) + _make_handwriting_variants(image)
        raw      = _run_ocr(variants, handwriting=True)
        raw      = _clean(raw)

        if not raw:
            return "No text detected in the image. Try a higher-resolution scan."

        corrected = _llm_correct_handwriting(raw, context_hint)
        corrected = _clean(corrected)
        return corrected

    except Exception as e:
        return f"Handwriting read failed: {e}"


def explain_screen(region=None, question: str = "") -> str:
    """
    Capture the screen (or a region) and explain what is on it using the LLM.

    If a vision model (LLaVA, Moondream, etc.) is available in Ollama, the
    raw screenshot is sent to it for a full visual description.

    If no vision model is installed, the screen is OCR'd and the LLM is asked
    to describe the content based on the extracted text.

    Parameters
    ----------
    region   : (left, top, width, height) or None for full screen
    question : optional specific question e.g. "what application is open?"

    Returns
    -------
    Human-readable explanation of what is on the screen.
    """
    err = _check_deps()
    if err:
        return err

    try:
        image = _capture(region)

        if not question:
            question = (
                "Please describe what is currently on this computer screen in detail. "
                "Include: what application is open, what content is visible, "
                "any text or buttons present, and what the user appears to be doing. "
                "Be thorough and specific to assist a visually impaired user."
            )
        else:
            question = (
                f"Looking at this computer screen, please answer: {question}\n"
                "Be specific and descriptive to help a visually impaired user understand "
                "exactly what is on screen."
            )

        return _explain_with_vision(image, question)

    except Exception as e:
        return f"Screen explanation failed: {e}"


def explain_screen_region(left: int, top: int, width: int, height: int,
                          question: str = "") -> str:
    """Explain a specific screen region."""
    return explain_screen(region=(left, top, width, height), question=question)
