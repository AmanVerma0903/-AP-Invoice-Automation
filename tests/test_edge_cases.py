"""End-to-end automated tests for all four designed edge cases."""

import os
from decimal import Decimal
import pytest
from database.db import init_db, find_po_by_number, get_invoices_history
from services.audit_service import process_invoice_pipeline
from models.invoice import DecisionStatus


@pytest.fixture
def clean_test_db(tmp_path):
    db_path = str(tmp_path / "edge_case_test.db")
    init_db(db_path=db_path, force_reseed=True)
    return db_path


@pytest.fixture
def samples_dir():
    return os.path.join(os.path.dirname(os.path.dirname(__file__)), "sample_invoices")


def test_edge_case_1_duplicate_invoice(clean_test_db, samples_dir):
    """Edge Case 1: Duplicate Invoice Submission.
    
    Uploading original invoice, followed by a resubmission (with different filename)
    must detect duplicate, place on ON_HOLD, and NOT double-consume PO balance.
    """
    orig_path = os.path.join(samples_dir, "02_duplicate_original_glp.pdf")
    resub_path = os.path.join(samples_dir, "02_duplicate_resubmission_glp_renamed.pdf")

    with open(orig_path, "rb") as f:
        orig_bytes = f.read()
    with open(resub_path, "rb") as f:
        resub_bytes = f.read()

    # 1. Process Original Invoice
    res1 = process_invoice_pipeline("02_duplicate_original_glp.pdf", orig_bytes, db_path=clean_test_db)
    assert res1.decision.status == DecisionStatus.APPROVAL_ELIGIBLE
    
    # Check PO-2026-103 balance was consumed (was $8,400.00, now $0.00)
    po1 = find_po_by_number("PO-2026-103", db_path=clean_test_db)
    assert Decimal(str(po1["remaining_balance"])) == Decimal("0.00")

    # 2. Process Duplicate Re-submission (different filename, same invoice number & vendor)
    res2 = process_invoice_pipeline("02_duplicate_resubmission_glp_renamed.pdf", resub_bytes, db_path=clean_test_db)
    assert res2.decision.status == DecisionStatus.ON_HOLD
    assert "duplicate" in res2.decision.primary_reason.lower()

    # Verify PO balance was NOT deducted again (still $0.00, not negative!)
    po2 = find_po_by_number("PO-2026-103", db_path=clean_test_db)
    assert Decimal(str(po2["remaining_balance"])) == Decimal("0.00")


def test_edge_case_2_multiple_invoices_against_single_po(clean_test_db, samples_dir):
    """Edge Case 2: Multiple Invoices Against One PO.
    
    PO-2026-102 total is $12,500.00.
    - Invoice 1: $5,000.00 -> Approved, remaining balance $7,500.00.
    - Invoice 2: $7,500.00 -> Approved, remaining balance $0.00.
    - Invoice 3: $3,000.00 -> Exceeds balance -> REVIEW_REQUIRED.
    """
    p1 = os.path.join(samples_dir, "03a_split_po_milestone1_datacore.pdf")
    p2 = os.path.join(samples_dir, "03b_split_po_milestone2_datacore.pdf")
    p3 = os.path.join(samples_dir, "03c_split_po_overdraft_datacore.pdf")

    with open(p1, "rb") as f:
        b1 = f.read()
    with open(p2, "rb") as f:
        b2 = f.read()
    with open(p3, "rb") as f:
        b3 = f.read()

    # Step 1: Milestone 1 ($5,000.00)
    res1 = process_invoice_pipeline("03a_split_po_milestone1_datacore.pdf", b1, db_path=clean_test_db)
    assert res1.decision.status == DecisionStatus.APPROVAL_ELIGIBLE
    po_after_1 = find_po_by_number("PO-2026-102", db_path=clean_test_db)
    assert Decimal(str(po_after_1["remaining_balance"])) == Decimal("7500.00")

    # Step 2: Milestone 2 ($7,500.00)
    res2 = process_invoice_pipeline("03b_split_po_milestone2_datacore.pdf", b2, db_path=clean_test_db)
    assert res2.decision.status == DecisionStatus.APPROVAL_ELIGIBLE
    po_after_2 = find_po_by_number("PO-2026-102", db_path=clean_test_db)
    assert Decimal(str(po_after_2["remaining_balance"])) == Decimal("0.00")

    # Step 3: Overdraft Invoice ($3,000.00)
    res3 = process_invoice_pipeline("03c_split_po_overdraft_datacore.pdf", b3, db_path=clean_test_db)
    assert res3.decision.status == DecisionStatus.REVIEW_REQUIRED
    assert "exceeds" in res3.decision.primary_reason.lower()

    # Step 4: Verify PO balance remains $0.00 and was not corrupted
    po_after_3 = find_po_by_number("PO-2026-102", db_path=clean_test_db)
    assert Decimal(str(po_after_3["remaining_balance"])) == Decimal("0.00")


def test_edge_case_3_amount_discrepancy_and_tolerance(clean_test_db, samples_dir):
    """Edge Case 3: Amount Discrepancy & Tolerance Boundary against PO-2026-101 ($5,000).
    
    - 4a ($5,035.00): Within $50.00 tolerance -> APPROVAL_ELIGIBLE with note.
    - 4b ($5,450.00): Exceeds $50.00 tolerance (+$450.00) -> REVIEW_REQUIRED.
    """
    within_path = os.path.join(samples_dir, "04a_within_tolerance_apex.pdf")
    exceeds_path = os.path.join(samples_dir, "04b_exceeds_tolerance_apex.pdf")

    with open(within_path, "rb") as f:
        w_bytes = f.read()
    with open(exceeds_path, "rb") as f:
        e_bytes = f.read()

    # 4a: Within tolerance
    res_w = process_invoice_pipeline("04a_within_tolerance_apex.pdf", w_bytes, db_path=clean_test_db)
    assert res_w.decision.status == DecisionStatus.APPROVAL_ELIGIBLE
    assert res_w.po_match.within_tolerance is True
    assert res_w.po_match.amount_variance == Decimal("35.00")

    # 4b: Exceeds tolerance
    res_e = process_invoice_pipeline("04b_exceeds_tolerance_apex.pdf", e_bytes, db_path=clean_test_db)
    assert res_e.decision.status == DecisionStatus.REVIEW_REQUIRED
    assert res_e.po_match.within_tolerance is False
    assert res_e.po_match.amount_variance == Decimal("450.00")
    assert "exceed" in res_e.decision.primary_reason.lower() or "tolerance" in res_e.decision.primary_reason.lower()


def test_edge_case_4_missing_invoice_data(clean_test_db, samples_dir):
    """Edge Case 4: Missing Mandatory Invoice Data.
    
    Invoice has missing invoice number -> Placed ON_HOLD, never invents number,
    identifies missing fields, provides reviewer next actions.
    """
    missing_path = os.path.join(samples_dir, "05_missing_invoice_number_apex.pdf")
    with open(missing_path, "rb") as f:
        m_bytes = f.read()

    res = process_invoice_pipeline("05_missing_invoice_number_apex.pdf", m_bytes, db_path=clean_test_db)
    assert res.decision.status == DecisionStatus.ON_HOLD
    assert res.extracted_data.invoice_number is None
    assert any("invoice number" in r.lower() for r in res.decision.all_reasons)
    assert len(res.decision.suggested_actions) > 0
