"""Normalization utilities for invoice fields."""

import re
from decimal import Decimal, ROUND_HALF_UP
from datetime import date, datetime
from typing import Optional, Dict, Any
from dateutil import parser as date_parser


CORP_SUFFIXES = [
    r"\bllc\b",
    r"\binc\b",
    r"\bincorporated\b",
    r"\bcorp\b",
    r"\bcorporation\b",
    r"\bltd\b",
    r"\blimited\b",
    r"\bsas\b",
    r"\bgmbh\b",
    r"\bco\b",
    r"\bcompany\b",
]


def normalize_vendor_name(name: Optional[str]) -> str:
    """Normalize vendor name for conservative lookup matching.
    
    Preserves original name for legal records, but standardizes case, punctuation,
    and trailing entity suffixes to avoid trivial mismatch errors.
    """
    if not name:
        return ""
    
    normalized = name.lower().strip()
    # Remove commas, periods, hyphens
    normalized = re.sub(r"[\.,\-_/\\#@!]", " ", normalized)
    
    # Remove common corporate suffixes
    for suffix in CORP_SUFFIXES:
        normalized = re.sub(suffix, " ", normalized, flags=re.IGNORECASE)
        
    # Collapse multiple spaces
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


def normalize_date(date_val: Any) -> Optional[date]:
    """Parse various date string formats into standard datetime.date.
    
    Correctly handles Indian and UK DD.MM.YYYY or DD/MM/YYYY formats.
    """
    if not date_val:
        return None
    if isinstance(date_val, date) and not isinstance(date_val, datetime):
        return date_val
    if isinstance(date_val, datetime):
        return date_val.date()
        
    cleaned = str(date_val).strip()
    if not cleaned or cleaned.lower() == "none":
        return None

    # Handle explicit DD.MM.YYYY e.g. 14.09.2026
    dot_match = re.match(r"^(\d{1,2})\.(\d{1,2})\.(\d{2,4})$", cleaned)
    if dot_match:
        d, m, y = int(dot_match.group(1)), int(dot_match.group(2)), int(dot_match.group(3))
        if y < 100:
            y += 2000
        try:
            return date(y, m, d)
        except ValueError:
            pass
        
    try:
        # Use dayfirst=True for international standard compliance (DD/MM/YYYY)
        dt = date_parser.parse(cleaned, dayfirst=True)
        return dt.date()
    except (ValueError, TypeError, OverflowError):
        pass

    try:
        dt = date_parser.parse(cleaned, dayfirst=False)
        return dt.date()
    except (ValueError, TypeError, OverflowError):
        return None


def normalize_currency(curr_val: Optional[str]) -> str:
    """Normalize currency symbols and codes to ISO 3-letter codes."""
    if not curr_val:
        return "USD"
        
    curr = curr_val.strip().upper()
    if curr in ("$", "US$", "USD"):
        return "USD"
    if curr in ("€", "EUR"):
        return "EUR"
    if curr in ("£", "GBP"):
        return "GBP"
    if curr in ("₹", "INR", "RS", "RS.") or "₹" in curr_val or "INR" in curr:
        return "INR"
    if curr in ("C$", "CAD"):
        return "CAD"
    if curr in ("A$", "AUD"):
        return "AUD"
    return curr[:3]


def to_decimal(val: Any) -> Optional[Decimal]:
    """Convert amount to exact Decimal with 2 decimal places."""
    if val is None:
        return None
    if isinstance(val, Decimal):
        return val.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        
    raw_str = str(val).strip()
    if not raw_str or raw_str.lower() == "none":
        return None

    # Strip currency signs (₹, $, €, £), currency names (INR, USD), and thousand commas
    cleaned = re.sub(r"[₹\$\€\£]|inr|rs\.?|usd|eur|gbp", "", raw_str, flags=re.IGNORECASE)
    cleaned = cleaned.replace(",", "").strip()
    if not cleaned:
        return None
        
    try:
        d = Decimal(cleaned)
        return d.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except Exception:
        return None


def normalize_invoice_payload(raw_data: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize complete extracted dictionary while preserving raw values."""
    vendor_name = raw_data.get("vendor_name")
    raw_date = raw_data.get("invoice_date")
    raw_curr = raw_data.get("currency")
    
    return {
        "raw_vendor_name": vendor_name,
        "normalized_vendor_name": normalize_vendor_name(vendor_name),
        "normalized_invoice_date": normalize_date(raw_date),
        "normalized_currency": normalize_currency(raw_curr),
        "subtotal_dec": to_decimal(raw_data.get("subtotal")),
        "tax_amount_dec": to_decimal(raw_data.get("tax_amount")),
        "total_amount_dec": to_decimal(raw_data.get("total_amount")),
    }
