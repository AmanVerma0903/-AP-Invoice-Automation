"""Master regression test suite covering the three sample invoice cases and Gemini/Local modes.

Mandatory Regression Tests:
- Test A: Kent RO Systems Limited
- Test B: Adidas India Marketing Private Limited + Separate Flipkart Bill of Supply (Multi-doc Boundary)
- Test C: DEMO - Sliced Invoices
- Test D: Gemini Mode with Mocked API Success
- Test E: Gemini Failure Mode C with Graceful Offline Fallback
"""

import os
import pytest
from decimal import Decimal
from datetime import date
from unittest.mock import patch, MagicMock

from services.pdf_extractor import extract_text_from_pdf, detect_document_boundaries
from services.llm_extractor import extract_deterministically, extract_invoice_data, extract_with_gemini
from services.audit_service import process_invoice_pipeline
from models.invoice import DecisionStatus, CheckStatus, ExtractedInvoice
from database.db import init_db


@pytest.fixture
def clean_db(tmp_path):
    db_file = str(tmp_path / "regression_test.db")
    init_db(db_file, force_reseed=True)
    return db_file


@pytest.fixture
def sample_paths():
    base = os.path.join(os.path.dirname(__file__), "..", "sample_invoices")
    return {
        "kent": os.path.abspath(os.path.join(base, "kent_invoice.pdf")),
        "adidas": os.path.abspath(os.path.join(base, "adidas_flipkart_multidoc.pdf")),
        "sliced": os.path.abspath(os.path.join(base, "sliced_invoices.pdf")),
    }


# =============================================================================
# TEST A: KENT RO INVOICE (LOCAL FALLBACK MODE)
# =============================================================================
def test_regression_kent_ro_local_fallback(sample_paths, clean_db, monkeypatch):
    """Test A: Verify Kent RO invoice extraction and disposition in local-only fallback mode."""
    # Ensure Gemini API key is absent (local fallback mode)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    pdf_path = sample_paths["kent"]
    assert os.path.exists(pdf_path), f"Kent RO sample PDF not found at {pdf_path}"

    with open(pdf_path, "rb") as f:
        file_bytes = f.read()

    result = process_invoice_pipeline("kent_invoice.pdf", file_bytes, db_path=clean_db)
    ext = result.extracted_data

    # 1. Vendor Name
    assert ext.vendor_name == "Kent RO Systems Limited", f"Expected 'Kent RO Systems Limited', got '{ext.vendor_name}'"
    assert "original for recipient" not in (ext.vendor_name or "").lower()

    # 2. Invoice & Order Identifiers
    assert ext.invoice_number == "HYD8-1236", f"Expected 'HYD8-1236', got '{ext.invoice_number}'"
    assert ext.order_number == "405-3123402-7766752", f"Expected '405-3123402-7766752', got '{ext.order_number}'"

    # 3. Date & Currency
    assert ext.invoice_date == date(2026, 9, 14), f"Expected 2026-09-14, got {ext.invoice_date}"
    assert ext.currency == "INR", f"Expected currency 'INR', got '{ext.currency}'"

    # 4. Financial Calculations (Decimal)
    assert ext.subtotal == Decimal("2770.34"), f"Expected subtotal 2770.34, got {ext.subtotal}"
    assert ext.tax_amount == Decimal("498.66"), f"Expected tax 498.66, got {ext.tax_amount}"
    assert ext.total_amount == Decimal("3269.00"), f"Expected total 3269.00, got {ext.total_amount}"
    assert (ext.subtotal + ext.tax_amount) == ext.total_amount

    # 5. Line Item
    assert len(ext.line_items) >= 1
    item = ext.line_items[0]
    assert "KENT Digi Plus Air Fryer" in item.description
    assert item.quantity == Decimal("1")
    assert item.amount == Decimal("2770.34")

    # 6. Business Decision: Deterministic Unlisted Vendor / Missing PO
    # Vendor is not in approved list and has no PO -> Must NOT be marked APPROVAL_ELIGIBLE
    assert result.decision.status == DecisionStatus.REVIEW_REQUIRED
    assert "Kent RO Systems Limited" in result.decision.primary_reason


# =============================================================================
# TEST B: ADIDAS INVOICE + SEPARATE FLIPKART BILL OF SUPPLY (MULTI-DOC)
# =============================================================================
def test_regression_adidas_and_flipkart_multidoc(sample_paths, clean_db, monkeypatch):
    """Test B: Verify Adidas invoice and Flipkart Bill of Supply separation."""
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    pdf_path = sample_paths["adidas"]
    assert os.path.exists(pdf_path), f"Adidas sample PDF not found at {pdf_path}"

    with open(pdf_path, "rb") as f:
        file_bytes = f.read()

    # 1. Low-level text extraction and boundary detection
    doc_info = extract_text_from_pdf(file_bytes)
    assert doc_info["page_count"] == 3
    boundaries = doc_info["document_boundaries"]

    # Verify that multi-document boundaries are detected
    assert len(boundaries) == 2, f"Expected 2 documents in PDF, detected {len(boundaries)}: {boundaries}"
    assert boundaries[0] == [0]  # Page 1: Adidas
    assert boundaries[1] == [1, 2]  # Pages 2 & 3: Flipkart Bill of Supply

    # 2. Pipeline Execution
    result = process_invoice_pipeline("adidas_flipkart_multidoc.pdf", file_bytes, db_path=clean_db)
    ext = result.extracted_data

    # Primary Document: Adidas India Marketing Private Limited
    assert ext.vendor_name == "Adidas India Marketing Private Limited"
    assert ext.invoice_number == "INMYIN0004694699"
    assert ext.order_number == "IR_MY_AIN5397497"
    assert ext.order_number.lower() != "info"
    assert ext.invoice_date == date(2026, 6, 17)
    assert ext.currency == "INR"
    assert ext.subtotal == Decimal("2711.02")
    assert ext.tax_amount == Decimal("487.98")
    assert ext.total_amount == Decimal("3199.00")
    assert ext.gstin == "06AAACA5313P1ZP"
    assert ext.pan == "AAACA5313P"

    # Line item for Adidas
    assert len(ext.line_items) >= 1
    ad_item = ext.line_items[0]
    assert "Lightweight trainers" in ad_item.description or "adidas" in ad_item.description.lower()
    assert ad_item.quantity == Decimal("1")
    assert ad_item.amount == Decimal("2711.02")

    # 3. Document Separation: Flipkart Bill of Supply
    # Flipkart's ₹230 must NOT be added to Adidas's ₹3199
    assert len(result.sub_results) == 1, "Expected 1 subdocument (Flipkart) to be preserved separately"
    sub_res = result.sub_results[0]
    sub_ext = sub_res.extracted_data

    assert "Flipkart India Private Limited" in (sub_ext.vendor_name or "")
    assert sub_ext.total_amount == Decimal("230.00")
    assert sub_ext.currency == "INR"
    assert sub_ext.total_amount != ext.total_amount  # Separate figures


# =============================================================================
# TEST C: SLICED INVOICES SAMPLE (LOCAL FALLBACK MODE)
# =============================================================================
def test_regression_sliced_invoices_local_fallback(sample_paths, clean_db, monkeypatch):
    """Test C: Verify Sliced Invoices parsing in local fallback mode."""
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    pdf_path = sample_paths["sliced"]
    assert os.path.exists(pdf_path), f"Sliced Invoices PDF not found at {pdf_path}"

    with open(pdf_path, "rb") as f:
        file_bytes = f.read()

    result = process_invoice_pipeline("sliced_invoices.pdf", file_bytes, db_path=clean_db)
    ext = result.extracted_data

    # 1. Vendor: Must NOT be "From:"
    assert ext.vendor_name == "DEMO - Sliced Invoices", f"Expected 'DEMO - Sliced Invoices', got '{ext.vendor_name}'"
    assert ext.vendor_name.lower() != "from:"

    # 2. Invoice Number: Must preserve "INV-" prefix!
    assert ext.invoice_number == "INV-3337", f"Expected 'INV-3337', got '{ext.invoice_number}'"

    # 3. Order Number
    assert ext.order_number == "12345", f"Expected '12345', got '{ext.order_number}'"

    # 4. Dates
    assert ext.invoice_date == date(2016, 1, 25), f"Expected 2016-01-25, got {ext.invoice_date}"
    assert ext.due_date == date(2016, 1, 31), f"Expected 2016-01-31, got {ext.due_date}"

    # 5. Currency & Financials
    assert ext.currency == "USD"
    # Subtotal must be 85.00, NOT 1.00 (from quantity)
    assert ext.subtotal == Decimal("85.00"), f"Expected subtotal 85.00, got {ext.subtotal}"
    assert ext.tax_amount == Decimal("8.50"), f"Expected tax 8.50, got {ext.tax_amount}"
    assert ext.total_amount == Decimal("93.50"), f"Expected total 93.50, got {ext.total_amount}"
    assert (ext.subtotal + ext.tax_amount) == ext.total_amount

    # 6. Line Item
    assert len(ext.line_items) >= 1
    item = ext.line_items[0]
    assert "Web Design" in item.description
    assert item.quantity == Decimal("1.00")
    assert item.unit_price == Decimal("85.00")
    assert item.amount == Decimal("85.00")


# =============================================================================
# TEST D: GEMINI AI EXTRACTION MODE (MOCKED RESPONSE)
# =============================================================================
def test_gemini_mode_mocked_success(monkeypatch):
    """Test D: Verify Gemini structured output parsing when API call succeeds."""
    monkeypatch.setenv("GEMINI_API_KEY", "test-mock-gemini-key-12345")
    monkeypatch.setenv("GEMINI_MODEL", "gemini-2.5-flash")

    mock_gemini_json = """{
        "document_type": "Tax Invoice",
        "vendor_name": "Kent RO Systems Limited",
        "vendor_tax_id": "36AADCK0743L1ZH",
        "gstin": "36AADCK0743L1ZH",
        "pan": "AADCK0743L",
        "invoice_number": "HYD8-1236",
        "order_number": "405-3123402-7766752",
        "invoice_date": "2026-09-14",
        "due_date": null,
        "currency": "INR",
        "po_reference": null,
        "subtotal": 2770.34,
        "tax_amount": 498.66,
        "tax_breakdown": {"IGST": 498.66},
        "total_amount": 3269.00,
        "amount_payable": 3269.00,
        "line_items": [
            {"description": "KENT Digi Plus Air Fryer", "quantity": 1, "unit_price": 2770.34, "amount": 2770.34}
        ]
    }"""

    mock_response = MagicMock()
    mock_response.text = mock_gemini_json

    mock_client = MagicMock()
    mock_client.models.generate_content.return_value = mock_response

    with patch("google.genai.Client", return_value=mock_client):
        ext, warning = extract_with_gemini("Dummy invoice text layer")

    assert warning is None
    assert ext is not None
    assert ext.vendor_name == "Kent RO Systems Limited"
    assert ext.invoice_number == "HYD8-1236"
    assert ext.subtotal == Decimal("2770.34")
    assert ext.tax_amount == Decimal("498.66")
    assert ext.total_amount == Decimal("3269.00")
    assert ext.currency == "INR"
    assert ext.extraction_method == "Gemini AI (gemini-2.5-flash)"
    assert ext.extraction_confidence == 0.98


# =============================================================================
# TEST E: GEMINI FAILURE & GRACEFUL OFFLINE FALLBACK (MODE C)
# =============================================================================
def test_gemini_mode_c_graceful_fallback(monkeypatch, sample_paths):
    """Test E: Verify that when Gemini API request throws an error, it falls back to local pipeline."""
    secret_key = "AIzaSySecretKeyNeverExpose"
    monkeypatch.setenv("GEMINI_API_KEY", secret_key)
    monkeypatch.setenv("GEMINI_MODEL", "gemini-2.5-flash")

    pdf_path = sample_paths["sliced"]
    doc_info = extract_text_from_pdf(pdf_path)
    raw_text = doc_info["raw_text"]

    # Simulate a Gemini API QuotaExceeded or RateLimit 429 error
    mock_client = MagicMock()
    mock_client.models.generate_content.side_effect = Exception("429 ResourceExhausted: Quota limit exceeded for free tier")

    with patch("google.genai.Client", return_value=mock_client):
        # Must gracefully fall back to local extraction without crashing
        ext = extract_invoice_data(raw_text)

    assert ext is not None
    # Verified that local extraction succeeded
    assert ext.vendor_name == "DEMO - Sliced Invoices"
    assert ext.invoice_number == "INV-3337"
    assert ext.total_amount == Decimal("93.50")
    # Warning attached
    assert any("Gemini API request failed" in w for w in ext.extraction_warnings)
    # Ensure secret key is NEVER leaked in any warning
    for w in ext.extraction_warnings:
        assert secret_key not in w


# =============================================================================
# TEST F: FORCE OFFLINE OVERRIDE TOGGLE (USER UI SWITCH)
# =============================================================================
def test_force_offline_mode_override(monkeypatch, sample_paths):
    """Test F: Verify that when force_offline=True, extraction strictly bypasses Gemini even if key is present."""
    monkeypatch.setenv("GEMINI_API_KEY", "dummy_configured_key_for_testing")
    monkeypatch.setenv("GEMINI_MODEL", "gemini-3.5-flash")

    pdf_path = sample_paths["sliced"]
    doc_info = extract_text_from_pdf(pdf_path)
    raw_text = doc_info["raw_text"]

    # When force_offline=True, extract_invoice_data must NOT call extract_with_gemini
    with patch("services.llm_extractor.extract_with_gemini") as mock_gemini:
        ext = extract_invoice_data(raw_text, force_offline=True)
        # Gemini should NEVER be invoked
        mock_gemini.assert_not_called()

    assert ext is not None
    assert ext.extraction_method == "Local Fallback (Heuristic & Layout)"
    assert ext.vendor_name == "DEMO - Sliced Invoices"
    assert ext.invoice_number == "INV-3337"
    assert ext.total_amount == Decimal("93.50")

