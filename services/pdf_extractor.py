import sys
import hashlib
import logging
from typing import Dict, Any, Tuple, List, Optional

# Prevent pymupdf.layout optional plugin from attempting heavy ONNX model memory allocation
sys.modules["pymupdf.layout"] = None
try:
    import fitz as pymupdf
except ImportError:
    import pymupdf

from services.ocr_service import run_ocr_on_pdf_page

logger = logging.getLogger(__name__)

MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB
MIN_TEXT_CHARS_THRESHOLD = 50  # Below this, page is considered scanned or image-based


def compute_file_hash(file_bytes_or_path: Any) -> str:
    """Compute SHA-256 hexadecimal digest of file content (accepts bytes or file path)."""
    if isinstance(file_bytes_or_path, str):
        with open(file_bytes_or_path, "rb") as f:
            data = f.read()
    else:
        data = file_bytes_or_path
    sha = hashlib.sha256()
    sha.update(data)
    return sha.hexdigest()


def validate_pdf_file(file_name: str, file_bytes: bytes) -> Tuple[bool, Optional[str]]:
    """Validate PDF file size and binary header."""
    if len(file_bytes) == 0:
        return False, "File is completely empty (0 bytes)."
    
    if len(file_bytes) > MAX_FILE_SIZE_BYTES:
        return False, f"File exceeds maximum allowed size of 10MB ({len(file_bytes) / (1024 * 1024):.2f}MB)."
    
    # Check PDF magic bytes (%PDF)
    if not file_bytes.startswith(b"%PDF"):
        return False, "Invalid file format: File does not have a valid PDF header."
        
    return True, None


def detect_document_boundaries(pages: List[str]) -> List[List[int]]:
    """Detect boundaries when multiple distinct documents are contained within a single PDF.
    
    Returns a list of 0-indexed page number lists for each document, e.g. [[0], [1, 2]].
    """
    if not pages:
        return []
    if len(pages) == 1:
        return [[0]]

    import re
    doc_groups: List[List[int]] = []
    current_group: List[int] = [0]

    for i in range(1, len(pages)):
        prev_txt = pages[i - 1]
        curr_txt = pages[i]
        is_new_doc = False

        # 1. Page numbering restarts (e.g., '1 of 2', 'Page 1 of 1')
        if re.search(r"(?i)\b1\s+of\s+\d+\b", curr_txt) or re.search(r"(?i)\bpage\s+1\s+of\b", curr_txt):
            is_new_doc = True

        # 2. Document type shift (e.g. Tax Invoice followed by Bill of Supply)
        has_curr_bill_of_supply = "bill of supply" in curr_txt.lower()
        has_prev_bill_of_supply = "bill of supply" in prev_txt.lower()
        has_curr_tax_inv = "tax invoice" in curr_txt.lower()
        has_prev_tax_inv = "tax invoice" in prev_txt.lower()

        if has_curr_bill_of_supply and not has_prev_bill_of_supply:
            is_new_doc = True
        elif has_curr_tax_inv and not has_prev_tax_inv and i > 1:
            is_new_doc = True

        # 3. Explicit distinct vendor or consignor header
        curr_vendor_m = re.search(r"(?i)\b(?:billed\s+from|sold\s+by|consignor\s+details\s*:?)\s*[:\-]?\s*([^\n\*]+)", curr_txt)
        prev_vendor_m = re.search(r"(?i)\b(?:billed\s+from|sold\s+by|consignor\s+details\s*:?)\s*[:\-]?\s*([^\n\*]+)", prev_txt)
        if curr_vendor_m and prev_vendor_m:
            c_v = curr_vendor_m.group(1).strip().lower()
            p_v = prev_vendor_m.group(1).strip().lower()
            if c_v != p_v and len(c_v) >= 4 and len(p_v) >= 4:
                is_new_doc = True

        if is_new_doc:
            doc_groups.append(current_group)
            current_group = [i]
        else:
            current_group.append(i)

    doc_groups.append(current_group)
    return doc_groups


def extract_text_from_pdf(file_bytes_or_path: Any) -> Dict[str, Any]:
    """Extract raw machine-readable text and layout blocks from PDF bytes or path.
    
    If text density is too low, triggers OCR fallback.
    Returns:
        {
            "raw_text": str,
            "page_count": int,
            "pages": List[str],
            "document_boundaries": List[List[int]],
            "is_scanned": bool,
            "warnings": List[str],
            "file_hash": str,
            "metadata": Dict[str, Any]
        }
    """
    if isinstance(file_bytes_or_path, str):
        with open(file_bytes_or_path, "rb") as f:
            file_bytes = f.read()
    else:
        file_bytes = file_bytes_or_path

    file_hash = compute_file_hash(file_bytes)
    warnings: List[str] = []
    
    try:
        doc = pymupdf.open(stream=file_bytes, filetype="pdf")
    except Exception as e:
        logger.error(f"Failed to open PDF stream: {e}")
        return {
            "raw_text": "",
            "page_count": 0,
            "pages": [],
            "document_boundaries": [],
            "is_scanned": False,
            "warnings": [f"Corrupted or unreadable PDF document: {str(e)}"],
            "file_hash": file_hash,
            "metadata": {},
        }

    page_texts: List[str] = []
    is_scanned = False
    
    for page_idx, page in enumerate(doc):
        page_text = page.get_text("text").strip()
        
        # If very little native text, check if page is scanned/image
        if len(page_text) < MIN_TEXT_CHARS_THRESHOLD:
            logger.info(f"Page {page_idx + 1} has only {len(page_text)} chars. Attempting OCR...")
            ocr_text, ocr_warnings = run_ocr_on_pdf_page(page)
            warnings.extend(ocr_warnings)
            
            if len(ocr_text) > len(page_text):
                page_text = ocr_text
                is_scanned = True
            else:
                if not page_text:
                    warnings.append(f"Page {page_idx + 1} contains no extractable text and OCR yielded no results.")
                    is_scanned = True

        page_texts.append(page_text)

    combined_text = "\n\n--- PAGE BREAK ---\n\n".join(page_texts).strip()
    boundaries = detect_document_boundaries(page_texts)
    
    doc_metadata = doc.metadata or {}
    page_count = len(doc)
    doc.close()

    if not combined_text:
        warnings.append("No readable text could be extracted from this PDF.")

    return {
        "raw_text": combined_text,
        "page_count": page_count,
        "pages": page_texts,
        "document_boundaries": boundaries,
        "is_scanned": is_scanned,
        "warnings": warnings,
        "file_hash": file_hash,
        "metadata": doc_metadata,
    }

