"""Automated regression test suite using the real Kent RO Systems Limited invoice."""

import os
from decimal import Decimal
from datetime import date
import pytest

from services.pdf_extractor import extract_text_from_pdf
from services.llm_extractor import extract_deterministically
from services.po_matcher import match_purchase_order
from services.validator import run_all_validations
from services.decision_engine import evaluate_decision
from services.audit_service import process_invoice_pipeline
from models.invoice import DecisionStatus, CheckStatus
from database.db import init_db


@pytest.fixture(scope="module")
def kent_pdf_bytes():
    pdf_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "sample_invoices", "kent_invoice.pdf")
    assert os.path.exists(pdf_path), f"Kent RO invoice PDF not found at {pdf_path}"
    with open(pdf_path, "rb") as f:
        return f.read()


@pytest.fixture
def clean_db(tmp_path):
    db_path = str(tmp_path / "regression_test.db")
    init_db(db_path=db_path, force_reseed=True)
    return db_path


def test_kent_text_extraction(kent_pdf_bytes):
    """Verify that PyMuPDF extracts text layers from the Kent invoice."""
    doc_info = extract_text_from_pdf(kent_pdf_bytes)
    assert doc_info["page_count"] >= 1
    raw = doc_info["raw_text"]
    assert "Kent RO Systems Limited" in raw
    assert "HYD8-1236" in raw
    assert "405-3123402-7766752" in raw


def test_kent_field_extraction(kent_pdf_bytes):
    """Verify exact expected field extraction from the real Kent RO invoice."""
    doc_info = extract_text_from_pdf(kent_pdf_bytes)
    extracted = extract_deterministically(doc_info["raw_text"])

    # 1. Vendor Name: Never extract 'Tax Invoice/Bill of Supply' or '(Original for Recipient)'
    assert extracted.vendor_name == "Kent RO Systems Limited"
    assert "recipient" not in (extracted.vendor_name or "").lower()
    assert "tax invoice" not in (extracted.vendor_name or "").lower()

    # 2. Invoice Number
    assert extracted.invoice_number == "HYD8-1236"

    # 3. Order Number (Preserved separately from PO reference)
    assert extracted.order_number == "405-3123402-7766752"

    # 4. Purchase Order Reference should be None (not Amazon order number)
    assert extracted.po_reference is None

    # 5. Date normalized to ISO 2026-09-14 (not month/day swapped to 2026-10-14)
    assert extracted.invoice_date == date(2026, 9, 14)

    # 6. Currency inferred from ₹ / INR context (never default to USD)
    assert extracted.currency == "INR"

    # 7. Subtotal / Net Taxable Amount
    assert extracted.subtotal == Decimal("2770.34")

    # 8. Tax / IGST Amount
    assert extracted.tax_amount == Decimal("498.66")

    # 9. Total Payable Amount
    assert extracted.total_amount == Decimal("3269.00")

    # 10. Line Items: contains product and quantity
    assert len(extracted.line_items) >= 1
    air_fryer_item = extracted.line_items[0]
    assert "KENT Digi Plus Air Fryer" in air_fryer_item.description
    assert air_fryer_item.quantity == Decimal("1")
    assert air_fryer_item.amount == Decimal("2770.34")


def test_kent_missing_po_and_unregistered_vendor_behavior(kent_pdf_bytes, clean_db):
    """Verify decision pipeline behavior for an e-commerce invoice with missing procurement PO.
    
    Must route to REVIEW_REQUIRED (Manual Review) because the vendor is not yet in the approved
    master vendor records and no corporate purchase order exists. It must NOT be placed ON_HOLD
    as a fraudulent/blocked vendor or hallucinate approval.
    """
    res = process_invoice_pipeline("kent_invoice.pdf", kent_pdf_bytes, db_path=clean_db)

    # Status must be REVIEW_REQUIRED (Manual Review), NOT ON_HOLD
    assert res.decision.status == DecisionStatus.REVIEW_REQUIRED
    assert res.decision.display_label == "Manual Review"

    # PO Match must be False
    assert res.po_match.is_matched is False
    assert "procurement po is required" in res.po_match.explanation.lower()

    # Vendor approval check must flag unregistered vendor without blocking hold
    v_check = next(c for c in res.validation_checks if c.check_name == "VENDOR_APPROVAL_STATUS")
    assert v_check.status == CheckStatus.FAIL
    assert v_check.is_blocking is False  # Non-blocking -> routes to Review, not Hold

    # Suggested actions should advise locating PO / expense reimbursement and vendor onboarding
    assert any("order" in a.lower() or "po" in a.lower() for a in res.decision.suggested_actions)
    assert any("onboarding" in a.lower() or "vendor" in a.lower() for a in res.decision.suggested_actions)


def test_kent_arithmetic_consistency(kent_pdf_bytes):
    """Verify that extracted subtotal + tax equals total within 1 cent."""
    doc_info = extract_text_from_pdf(kent_pdf_bytes)
    extracted = extract_deterministically(doc_info["raw_text"])

    assert extracted.subtotal is not None
    assert extracted.tax_amount is not None
    assert extracted.total_amount is not None

    computed = extracted.subtotal + extracted.tax_amount
    assert computed == extracted.total_amount
    assert computed == Decimal("3269.00")
