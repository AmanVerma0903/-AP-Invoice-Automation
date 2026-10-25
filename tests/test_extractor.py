"""Tests for PDF text extraction and offline deterministic invoice parsing."""

import os
from decimal import Decimal
import pytest
from services.pdf_extractor import extract_text_from_pdf, validate_pdf_file
from services.llm_extractor import extract_deterministically


@pytest.fixture
def samples_dir():
    return os.path.join(os.path.dirname(os.path.dirname(__file__)), "sample_invoices")


def test_validate_pdf_file():
    valid_pdf_bytes = b"%PDF-1.4 sample content"
    is_valid, err = validate_pdf_file("test.pdf", valid_pdf_bytes)
    assert is_valid is True
    assert err is None

    empty_bytes = b""
    is_valid, err = validate_pdf_file("empty.pdf", empty_bytes)
    assert is_valid is False
    assert "empty" in err.lower()

    corrupt_bytes = b"NOT_A_PDF"
    is_valid, err = validate_pdf_file("corrupt.pdf", corrupt_bytes)
    assert is_valid is False
    assert "header" in err.lower()


def test_extract_happy_path_pdf(samples_dir):
    pdf_path = os.path.join(samples_dir, "01_happy_path_apex.pdf")
    assert os.path.exists(pdf_path)

    with open(pdf_path, "rb") as f:
        file_bytes = f.read()

    doc_info = extract_text_from_pdf(file_bytes)
    assert doc_info["page_count"] == 1
    assert "Apex Cloud Solutions" in doc_info["raw_text"]
    assert "INV-2026-001" in doc_info["raw_text"]
    assert "PO-2026-101" in doc_info["raw_text"]

    extracted = extract_deterministically(doc_info["raw_text"])
    assert extracted.vendor_name == "Apex Cloud Solutions LLC"
    assert extracted.invoice_number == "INV-2026-001"
    assert extracted.po_reference == "PO-2026-101"
    assert extracted.subtotal == Decimal("5000.00")
    assert extracted.total_amount == Decimal("5000.00")
    assert len(extracted.line_items) == 2


def test_extract_missing_invoice_number(samples_dir):
    pdf_path = os.path.join(samples_dir, "05_missing_invoice_number_apex.pdf")
    with open(pdf_path, "rb") as f:
        file_bytes = f.read()

    doc_info = extract_text_from_pdf(file_bytes)
    extracted = extract_deterministically(doc_info["raw_text"])
    assert extracted.invoice_number is None
    assert any("invoice identifier/number is missing" in w.lower() for w in extracted.extraction_warnings)
