"""
screen_tools.py  —  Hybrid screen reading, OCR, handwriting correction, and
                    LLM-powered screen explanation.

Reading strategy (hybrid mode):
  1. Windows Accessibility API  — fast, pixel-perfect for all text-based UIs
                                   (browsers, PDFs, Word, Kindle, VS Code …)
  2. OCR fallback               — for images, scanned books, screenshots,
                                   camera photos, dark-theme UIs

Public API:
  read_screen(region, llm_clean)      – Hybrid: accessibility → OCR fallback
  read_screen_accessibility(region)   – Accessibility-only read
  read_screen_ocr(region, llm_clean)  – OCR-only read
  read_screen_region(...)             – Hybrid read of a specific region
  read_screen_raw(region)             – Raw OCR without LLM cleanup
  screenshot_to_file(path)            – Save screenshot to disk
  last_screen_text()                  – Return last read result
  read_handwriting(path)              – OCR an image/scan, then LLM-correct it
  explain_screen(region, question)    – Describe screen using vision LLM
  explain_screen_region(...)          – Explain a specific region
"""

import os
import re
import ctypes
import base64
from datetime import datetime

# ── DPI awareness ────────────────────────────────────────────────────────────
# Qt 6 already sets DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 at startup,
# which is the highest DPI mode. Calling SetProcessDPIAware() again would
# conflict with Qt's COM initialization and log a harmless but noisy error.
# No action needed here — Qt handles it.

# ── PIL ───────────────────────────────────────────────────────────────────────
try:
    from PIL import Image, ImageEnhance, ImageOps, ImageFilter
    _PIL_OK = True
except ImportError:
    _PIL_OK = False

# ── mss — fast, DPI-correct screen capture ────────────────────────────────────
try:
    import mss
    _MSS_OK = True
except ImportError:
    _MSS_OK = False

# ── OpenCV — production-grade image preprocessing ─────────────────────────────
try:
    import cv2
    import numpy as np
    _CV2_OK = True
except ImportError:
    _CV2_OK = False

# ── Tesseract ─────────────────────────────────────────────────────────────────
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

# Best OCR config: LSTM engine, assume uniform block of text
_OCR_CONFIG     = "--oem 3 --psm 6"
_OCR_CONFIG_ALT = "--oem 3 --psm 4"   # column layout fallback


# ── dependency check ──────────────────────────────────────────────────────────

def _check_deps():
    if not _PIL_OK and not _MSS_OK:
        return "Neither Pillow nor mss installed. Run: pip install pillow mss"
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

def _capture_mss(region=None):
    """
    Capture using mss — faster and DPI-correct.
    Returns a PIL Image for compatibility with the rest of the pipeline.
    region: (left, top, width, height) or None for full primary monitor.
    """
    with mss.mss() as sct:
        if region:
            left, top, width, height = region
            monitor = {"left": left, "top": top, "width": width, "height": height}
        else:
            monitor = sct.monitors[1]   # primary monitor

        shot   = sct.grab(monitor)
        img_np = np.array(shot)                              # BGRA
        img_np = cv2.cvtColor(img_np, cv2.COLOR_BGRA2BGR)
        return Image.fromarray(cv2.cvtColor(img_np, cv2.COLOR_BGR2RGB))


def _capture_pil(region=None):
    """Fallback capture using Pillow ImageGrab."""
    from PIL import ImageGrab
    if region:
        left, top, width, height = region
        return ImageGrab.grab(
            bbox=(left, top, left + width, top + height),
            all_screens=True
        )
    return ImageGrab.grab(all_screens=True)


def _capture(region=None):
    """Capture screen — prefers mss+cv2, falls back to PIL."""
    if _MSS_OK and _CV2_OK:
        return _capture_mss(region)
    return _capture_pil(region)


# ── OpenCV preprocessing (primary path) ──────────────────────────────────────

def _preprocess_cv2(pil_image):
    """
    Production-grade preprocessing with OpenCV.
    Returns a list of (name, pil_image) variants for OCR.
    """
    # PIL → numpy BGR
    img_np = cv2.cvtColor(np.array(pil_image), cv2.COLOR_RGB2BGR)

    # 1. Grayscale
    gray = cv2.cvtColor(img_np, cv2.COLOR_BGR2GRAY)

    # 2. Upscale 2x — Tesseract accuracy drops sharply below ~150 DPI
    h, w = gray.shape
    gray2x = cv2.resize(gray, (w * 2, h * 2), interpolation=cv2.INTER_CUBIC)

    variants = []

    # 3. Sharpen
    sharpen_kernel = np.array([[0, -1, 0], [-1, 5, -1], [0, -1, 0]])
    sharp = cv2.filter2D(gray2x, -1, sharpen_kernel)
    variants.append(("sharp", Image.fromarray(sharp)))

    # 4. Adaptive threshold — handles dark themes and uneven lighting
    adaptive = cv2.adaptiveThreshold(
        gray2x, 255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        31, 2
    )
    variants.append(("adaptive", Image.fromarray(adaptive)))

    # 5. Inverted adaptive threshold — for light-on-dark (dark theme UIs)
    inv_gray2x = cv2.bitwise_not(gray2x)
    adaptive_inv = cv2.adaptiveThreshold(
        inv_gray2x, 255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        31, 2
    )
    variants.append(("adaptive_inv", Image.fromarray(adaptive_inv)))

    # 6. Simple binary threshold (fast fallback)
    _, binary = cv2.threshold(gray2x, 128, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    variants.append(("otsu", Image.fromarray(binary)))

    # 7. Denoised variant
    denoised = cv2.medianBlur(sharp, 3)
    variants.append(("denoised", Image.fromarray(denoised)))

    return variants


# ── PIL preprocessing (fallback when cv2 unavailable) ────────────────────────

def _make_variants_pil(image):
    """PIL-based variants — used only when OpenCV is not installed."""
    w, h  = image.size
    scale = max(2, int(2400 / w))
    big   = image.resize((w * scale, h * scale), Image.LANCZOS)
    gray  = big.convert("L")

    variants = [("plain_gray", gray)]

    inv_gray     = ImageOps.invert(gray)
    inv_contrast = ImageEnhance.Contrast(inv_gray).enhance(3.5)
    inv_sharp    = ImageEnhance.Sharpness(inv_contrast).enhance(3.0)
    variants.append(("inv_contrast", inv_sharp))

    threshold     = gray.point(lambda p: 255 if p > 128 else 0, '1')
    inv_threshold = inv_gray.point(lambda p: 255 if p > 100 else 0, '1')
    variants.append(("threshold_normal", threshold))
    variants.append(("threshold_inv", inv_threshold))

    denoised = inv_contrast.filter(ImageFilter.MedianFilter(size=3))
    variants.append(("denoised", denoised))

    return variants


def _make_variants(image):
    """Return preprocessing variants using best available method."""
    if _CV2_OK:
        return _preprocess_cv2(image)
    return _make_variants_pil(image)


# ── handwriting variants ──────────────────────────────────────────────────────

def _make_handwriting_variants(image):
    """Extra preprocessing tuned for handwritten text."""
    if _CV2_OK:
        img_np = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)
        gray   = cv2.cvtColor(img_np, cv2.COLOR_BGR2GRAY)
        h, w   = gray.shape
        scale  = max(3, int(3000 / w))
        big    = cv2.resize(gray, (w * scale, h * scale), interpolation=cv2.INTER_CUBIC)

        variants = []

        # Strong contrast + sharpening
        clahe   = cv2.createCLAHE(clipLimit=4.0, tileGridSize=(8, 8))
        equalized = clahe.apply(big)
        sharpen_k = np.array([[0, -1, 0], [-1, 5, -1], [0, -1, 0]])
        sharp     = cv2.filter2D(equalized, -1, sharpen_k)
        variants.append(("hw_sharp", Image.fromarray(sharp)))

        # Light threshold (light ink on white)
        _, thr_light = cv2.threshold(big, 160, 255, cv2.THRESH_BINARY)
        variants.append(("hw_thr_light", Image.fromarray(thr_light)))

        # Dark threshold (dark paper / faded ink)
        _, thr_dark = cv2.threshold(big, 100, 255, cv2.THRESH_BINARY)
        variants.append(("hw_thr_dark", Image.fromarray(thr_dark)))

        # Inverted + CLAHE for dark backgrounds
        inv       = cv2.bitwise_not(big)
        inv_clahe = clahe.apply(inv)
        variants.append(("hw_inv_clahe", Image.fromarray(inv_clahe)))

        # Denoised
        denoised = cv2.medianBlur(sharp, 3)
        variants.append(("hw_denoised", Image.fromarray(denoised)))

        return variants

    # PIL fallback
    w, h  = image.size
    scale = max(3, int(3000 / w))
    big   = image.resize((w * scale, h * scale), Image.LANCZOS)
    gray  = big.convert("L")

    contrast = ImageEnhance.Contrast(gray).enhance(4.0)
    sharp    = ImageEnhance.Sharpness(contrast).enhance(4.0)
    adaptive = gray.point(lambda p: 255 if p > 160 else 0, '1')
    adaptive_dark = gray.point(lambda p: 255 if p > 100 else 0, '1')
    inv_gray     = ImageOps.invert(gray)
    inv_contrast = ImageEnhance.Contrast(inv_gray).enhance(4.0)
    denoised     = sharp.filter(ImageFilter.MedianFilter(size=3))

    return [
        ("hw_contrast", sharp),
        ("hw_threshold_light", adaptive),
        ("hw_threshold_dark", adaptive_dark),
        ("hw_inv_contrast", inv_contrast),
        ("hw_denoised", denoised),
    ]


# ── OCR ───────────────────────────────────────────────────────────────────────

def _run_ocr(variants, handwriting=False) -> str:
    """Run Tesseract on every variant, return the richest result."""
    configs = [
        "--oem 3 --psm 6",   # LSTM, uniform block
        "--oem 3 --psm 4",   # LSTM, single column
        "--oem 3 --psm 11",  # LSTM, sparse text
    ]

    if handwriting:
        configs += [
            "--oem 1 --psm 6",   # legacy LSTM, better for cursive
            "--oem 1 --psm 13",  # raw line
        ]

    best = ""
    for _name, img in variants:
        for cfg in configs:
            try:
                text = pytesseract.image_to_string(
                    img, lang="eng", config=cfg
                ).strip()
                if len(text.replace(" ", "").replace("\n", "")) > \
                   len(best.replace(" ", "").replace("\n", "")):
                    best = text
            except Exception:
                continue
    return best


# ── text cleanup ──────────────────────────────────────────────────────────────

def _clean(text: str) -> str:
    """Remove junk characters and excessive blank lines."""
    # Strip non-printable / pure-symbol garbage lines
    lines    = text.splitlines()
    filtered = []
    for line in lines:
        stripped = line.strip()
        # Keep blank lines for spacing, but drop lines that are only symbols
        if stripped and re.fullmatch(r"[^\w\s]{3,}", stripped):
            continue
        filtered.append(line)

    # Collapse runs of 3+ blank lines into a single blank line
    out, prev_blank = [], False
    for line in filtered:
        blank = not line.strip()
        if blank and prev_blank:
            continue
        out.append(line)
        prev_blank = blank

    return "\n".join(out).strip()


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
        from core.config import get_setting

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
    More aggressive correction than _llm_clean.
    """
    if not raw or len(raw.strip()) < 5:
        return raw

    try:
        import ollama
        from core.config import get_setting

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
        from core.config import get_setting

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
        from core.config import get_setting

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


# ── screenshots folder ────────────────────────────────────────────────────────

def _screenshots_dir() -> str:
    try:
        from core.config import resource_path
        path = resource_path("screenshots")
    except Exception:
        path = os.path.join(os.path.dirname(__file__), "screenshots")
    os.makedirs(path, exist_ok=True)
    return path


# ══════════════════════════════════════════════════════════════════════════════
#  ACCESSIBILITY ENGINE (Layer 1 — fast, accurate for all text-based content)
# ══════════════════════════════════════════════════════════════════════════════

# Minimum text length from accessibility before we consider it "found"
_ACC_MIN_CHARS = 20

# comtypes is imported lazily inside functions only — importing it at module
# level triggers COM initialization which conflicts with Qt 6's own COM setup
# and produces an OleInitialize error. We check availability on first use.
_COMTYPES_OK = None   # None = unchecked, True/False after first attempt


def _check_comtypes() -> bool:
    global _COMTYPES_OK
    if _COMTYPES_OK is not None:
        return _COMTYPES_OK
    try:
        import comtypes.client  # noqa: F401
        _COMTYPES_OK = True
    except ImportError:
        _COMTYPES_OK = False
    return _COMTYPES_OK


def _read_accessibility_focused_window() -> str:
    """
    Read text from the currently focused window using the Windows
    UI Automation accessibility API (UIA).

    Works for: browsers, PDFs, Word, Excel, Kindle, VS Code, Notepad,
               any standard Win32/WPF/Qt/WinForms application.
    Does NOT work for: raw images, scanned PDFs, camera photos.
    """
    try:
        import comtypes.client
        UIAuto = comtypes.client.GetModule(
            "UIAutomationCore.dll"
        )
        IUIAutomation = comtypes.client.CreateObject(
            "{ff48dba4-60ef-4201-aa87-54103eef594e}",
            interface=UIAuto.IUIAutomation
        )

        # Get the focused window element
        focused = IUIAutomation.GetFocusedElement()
        root    = IUIAutomation.GetRootElement()

        # Walk the focused window subtree collecting text
        texts = []
        _collect_uia_text(root, IUIAutomation, UIAuto, texts, depth=0, max_depth=8)

        result = "\n".join(t for t in texts if t.strip())
        return _clean(result)

    except Exception:
        return ""


def _collect_uia_text(element, uia, UIAuto, texts, depth, max_depth):
    """Recursively walk UIA tree and collect text values."""
    if depth > max_depth:
        return
    try:
        # Try to get Name property (label / button text / heading)
        name = element.CurrentName
        if name and name.strip() and len(name.strip()) > 1:
            texts.append(name.strip())

        # Try TextPattern for editable / document text
        try:
            TEXT_PATTERN_ID = 10014
            pattern = element.GetCurrentPattern(TEXT_PATTERN_ID)
            if pattern:
                text_pattern = pattern.QueryInterface(UIAuto.IUIAutomationTextPattern)
                doc_range = text_pattern.DocumentRange
                chunk = doc_range.GetText(8192)
                if chunk and chunk.strip():
                    texts.append(chunk.strip())
        except Exception:
            pass

        # Walk children
        walker   = uia.ControlViewWalker
        child    = walker.GetFirstChildElement(element)
        while child:
            _collect_uia_text(child, uia, UIAuto, texts, depth + 1, max_depth)
            child = walker.GetNextSiblingElement(child)

    except Exception:
        pass


def _read_accessibility_pywinauto(region=None) -> str:
    """
    Fallback accessibility read using pywinauto (simpler API).
    Reads the active window\'s control tree for text.
    """
    try:
        from pywinauto import Desktop
        desktop  = Desktop(backend="uia")
        windows  = desktop.windows()

        texts = []
        for win in windows:
            try:
                if not win.is_active():
                    continue
                for ctrl in win.descendants():
                    try:
                        t = ctrl.window_text()
                        if t and t.strip() and len(t.strip()) > 1:
                            texts.append(t.strip())
                    except Exception:
                        pass
            except Exception:
                continue

        result = "\n".join(texts)
        return _clean(result)

    except Exception:
        return ""


def read_screen_accessibility(region=None) -> str:
    """
    Read screen text using Windows Accessibility API.

    Tries UIA first (most accurate), then pywinauto as fallback.
    Returns empty string if nothing found — caller should OCR in that case.

    Works for: browsers, Word, PDFs, Kindle, VS Code, any native UI app.
    Does NOT work for: raw images, scanned books, screenshots.
    """
    # Try UIA via comtypes first
    if _check_comtypes():
        text = _read_accessibility_focused_window()
        if text and len(text.strip()) >= _ACC_MIN_CHARS:
            return text

    # Try pywinauto fallback
    text = _read_accessibility_pywinauto(region)
    if text and len(text.strip()) >= _ACC_MIN_CHARS:
        return text

    return ""


# ══════════════════════════════════════════════════════════════════════════════
#  PUBLIC API — HYBRID + OCR
# ══════════════════════════════════════════════════════════════════════════════

def read_screen_ocr(region=None, llm_clean=True) -> str:
    """OCR-only read. Use when you know the content is image-based."""
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
        return _clean(text)
    except Exception as e:
        return f"OCR failed: {e}"


def read_screen(region=None, llm_clean=True) -> str:
    """
    HYBRID screen reader — industry-standard two-layer approach.

    Layer 1 — Accessibility API (fast, exact):
      Reads text directly from the UI element tree.
      Works for: browsers, PDFs, Word, Kindle, VS Code, any native app.

    Layer 2 — OCR fallback (universal):
      Used automatically when accessibility returns nothing.
      Works for: images, scanned books, screenshots, dark-theme UIs,
                 camera photos, handwritten notes on screen.

    region : (left, top, width, height) or None for full screen.
    """
    global _last_text

    # Layer 1: accessibility
    acc_text = read_screen_accessibility(region)
    if acc_text and len(acc_text.strip()) >= _ACC_MIN_CHARS:
        _last_text = acc_text
        return acc_text

    # Layer 2: OCR fallback
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

        text       = _llm_clean(raw) if llm_clean else raw
        text       = _clean(text)
        _last_text = text
        return text

    except Exception as e:
        return f"Screen read failed: {e}"


def read_screen_region(left: int, top: int, width: int, height: int) -> str:
    """Hybrid read of a specific screen region."""
    return read_screen(region=(left, top, width, height))


def read_screen_raw(region=None) -> str:
    """Raw OCR output without LLM cleanup (bypasses accessibility layer)."""
    return read_screen_ocr(region=region, llm_clean=False)


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


def read_handwriting(image_path: str, context_hint: str = "") -> str:
    """
    Read and correct handwritten text from an image file or book scan.

    Parameters
    ----------
    image_path   : path to the image file (jpg, png, tiff, etc.)
    context_hint : optional hint to help the LLM, e.g. "19th century letter"
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
    Falls back to OCR + LLM if no vision model is installed.

    Parameters
    ----------
    region   : (left, top, width, height) or None for full screen
    question : optional specific question e.g. "what application is open?"
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