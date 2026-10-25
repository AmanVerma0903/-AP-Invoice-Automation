"""Tests for decision engine and rule precedence."""

from decimal import Decimal
import pytest
from models.invoice import (
    ExtractedInvoice,
    ValidationCheck,
    POMatchResult,
    DecisionStatus,
    CheckStatus,
)
from services.decision_engine import evaluate_decision


def test_clean_pass_is_approval_eligible():
    ext = ExtractedInvoice(
        vendor_name="Apex Cloud Solutions LLC",
        invoice_number="INV-2026-001",
        total_amount=Decimal("5000.00"),
    )
    validations = [
        ValidationCheck(check_name="REQUIRED_FIELDS", status=CheckStatus.PASS, message="All present"),
        ValidationCheck(check_name="VENDOR_APPROVAL_STATUS", status=CheckStatus.PASS, message="Approved"),
        ValidationCheck(check_name="PURCHASE_ORDER_MATCH", status=CheckStatus.PASS, message="Matched PO-2026-101"),
    ]
    po_match = POMatchResult(
        po_number="PO-2026-101",
        is_matched=True,
        within_tolerance=True,
        amount_variance=Decimal("0.00"),
        tolerance_threshold_used=Decimal("50.00"),
    )

    dec = evaluate_decision(ext, validations, po_match)
    assert dec.status == DecisionStatus.APPROVAL_ELIGIBLE
    assert dec.display_label == "Eligible for Approval"
    assert "approved" in dec.primary_reason.lower()


def test_blocking_failure_precedence_on_hold():
    ext = ExtractedInvoice(
        vendor_name="Blacklisted Supply Co.",
        invoice_number="INV-BLK-404",
        total_amount=Decimal("3200.00"),
    )
    # Even if PO matched and arithmetic passed, a blocking check MUST yield ON_HOLD
    validations = [
        ValidationCheck(check_name="REQUIRED_FIELDS", status=CheckStatus.PASS, message="All present"),
        ValidationCheck(
            check_name="VENDOR_APPROVAL_STATUS",
            status=CheckStatus.FAIL,
            is_blocking=True,
            message="Vendor is BLOCKED in procurement records.",
        ),
        ValidationCheck(check_name="PURCHASE_ORDER_MATCH", status=CheckStatus.PASS, message="Matched"),
    ]
    po_match = POMatchResult(
        po_number="PO-2026-105",
        is_matched=True,
        within_tolerance=True,
    )

    dec = evaluate_decision(ext, validations, po_match)
    assert dec.status == DecisionStatus.ON_HOLD
    assert dec.display_label == "On Hold"
    assert "blocked" in dec.primary_reason.lower()


def test_tolerance_variance_yields_review_required():
    ext = ExtractedInvoice(
        vendor_name="Apex Cloud Solutions LLC",
        invoice_number="INV-003",
        total_amount=Decimal("5450.00"),
    )
    validations = [
        ValidationCheck(check_name="REQUIRED_FIELDS", status=CheckStatus.PASS, message="All present"),
        ValidationCheck(check_name="VENDOR_APPROVAL_STATUS", status=CheckStatus.PASS, message="Approved"),
        ValidationCheck(
            check_name="PO_AMOUNT_TOLERANCE",
            status=CheckStatus.FAIL,
            is_blocking=False,
            message="Variance $450.00 exceeds tolerance limit $50.00.",
        ),
    ]
    po_match = POMatchResult(
        po_number="PO-2026-101",
        is_matched=True,
        within_tolerance=False,
        amount_variance=Decimal("450.00"),
        tolerance_threshold_used=Decimal("50.00"),
        explanation="Variance exceeds tolerance limit.",
    )

    dec = evaluate_decision(ext, validations, po_match)
    assert dec.status == DecisionStatus.REVIEW_REQUIRED
    assert dec.display_label == "Manual Review"
    assert "exceeds" in dec.primary_reason.lower() or "tolerance" in dec.primary_reason.lower()


def test_cumulative_balance_overdraft_yields_review_required():
    ext = ExtractedInvoice(
        vendor_name="Datacore Infrastructure Inc.",
        invoice_number="INV-DC-903",
        total_amount=Decimal("3000.00"),
    )
    validations = [
        ValidationCheck(check_name="REQUIRED_FIELDS", status=CheckStatus.PASS, message="All present"),
        ValidationCheck(check_name="VENDOR_APPROVAL_STATUS", status=CheckStatus.PASS, message="Approved"),
        ValidationCheck(
            check_name="PO_BALANCE_SUFFICIENCY",
            status=CheckStatus.FAIL,
            is_blocking=False,
            message="Invoice total $3,000.00 exceeds remaining PO balance $0.00.",
        ),
    ]
    po_match = POMatchResult(
        po_number="PO-2026-102",
        is_matched=True,
        exceeds_remaining_balance=True,
        po_remaining_balance=Decimal("0.00"),
        explanation="Invoice total exceeds remaining unbilled PO balance.",
    )

    dec = evaluate_decision(ext, validations, po_match)
    assert dec.status == DecisionStatus.REVIEW_REQUIRED
    assert dec.display_label == "Manual Review"
    assert "exceeds" in dec.primary_reason.lower() or "balance" in dec.primary_reason.lower()


def test_human_reviewer_actions_lifecycle(tmp_path):
    """Test human-in-the-loop reviewer actions, overrides, and audit log tracking."""
    from database.db import init_db, apply_reviewer_decision, save_invoice_result, get_invoice_detail
    from datetime import datetime

    db_path = str(tmp_path / "reviewer_test.db")
    init_db(db_path, force_reseed=True)

    # Seed an invoice in REVIEW_REQUIRED state
    inv_dict = {
        "invoice_id": "INV-TEST-REV-001",
        "file_name": "test_variance.pdf",
        "file_hash": "dummy_hash_123",
        "extracted_data": {
            "vendor_name": "Apex Cloud Solutions LLC",
            "invoice_number": "INV-REV-99",
            "total_amount": 5450.00,
        },
        "normalized_data": {"vendor_id": "VEND-001"},
        "decision": {
            "status": "REVIEW_REQUIRED",
            "display_label": "Manual Review",
            "primary_reason": "Total differs by $450 exceeding tolerance.",
            "all_reasons": ["Total differs by $450"],
        },
        "po_match": {"po_number": "PO-2026-101"},
        "validation_checks": [],
    }
    save_invoice_result(inv_dict, db_path=db_path)

    # 1. Human Reviewer Overrides & Approves
    res = apply_reviewer_decision(
        invoice_id="INV-TEST-REV-001",
        action="MANUAL_OVERRIDE_APPROVE",
        reviewer_note="Approved by AP Lead: seasonal price increase accepted.",
        reviewer_name="Senior AP Auditor",
        db_path=db_path,
    )
    assert res["success"] is True
    assert res["new_status"] == "APPROVAL_ELIGIBLE"
    assert "Reviewer Override" in res["new_label"]

    # Verify database persistence
    detail = get_invoice_detail("INV-TEST-REV-001", db_path=db_path)
    assert detail["status"] == "APPROVAL_ELIGIBLE"
    assert detail["display_label"] == "Approved (Reviewer Override)"

    # Verify audit log entry
    reviewer_logs = [log for log in detail["audit_logs"] if "HUMAN_MANUAL_OVERRIDE_APPROVE" in log["event_type"]]
    assert len(reviewer_logs) == 1
    assert "seasonal price increase" in reviewer_logs[0]["description"]

