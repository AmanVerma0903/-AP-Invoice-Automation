"""OCR service using PyMuPDF pixmap and pytesseract with graceful fallback."""

import io
import logging
from typing import Tuple, List
from PIL import Image

logger = logging.getLogger(__name__)

# Check if pytesseract is available
try:
    import pytesseract
    PYTESSERACT_AVAILABLE = True
except ImportError:
    PYTESSERACT_AVAILABLE = False


def is_tesseract_configured() -> bool:
    """Check if pytesseract and the underlying OCR engine are usable."""
    if not PYTESSERACT_AVAILABLE:
        return False
    try:
        # Quick test to see if tesseract binary responds
        pytesseract.get_tesseract_version()
        return True
    except Exception:
        return False


def run_ocr_on_pdf_page(page) -> Tuple[str, List[str]]:
    """Convert PyMuPDF page to image and perform OCR using pytesseract.
    
    Returns:
        (extracted_text, warnings_list)
    """
    warnings = []
    
    if not PYTESSERACT_AVAILABLE:
        warnings.append("OCR package (pytesseract) is not installed.")
        return "", warnings

    if not is_tesseract_configured():
        warnings.append("Tesseract-OCR engine binary is not installed or not in system PATH. Scanned text extraction skipped.")
        return "", warnings

    try:
        # PyMuPDF direct pixmap rendering (no poppler dependency needed!)
        pix = page.get_pixmap(dpi=300)
        img = Image.open(io.BytesIO(pix.tobytes("png")))
        
        # Run OCR
        text = pytesseract.image_to_string(img)
        return text.strip(), warnings
    except Exception as e:
        logger.warning(f"OCR execution failed on page: {e}")
        warnings.append(f"OCR execution failed: {str(e)}")
        return "", warnings
