"""Tests for deterministic validation engine."""

import os
from decimal import Decimal
from datetime import date
import pytest

from models.invoice import (
    ExtractedInvoice,
    LineItem,
    CheckStatus,
    POMatchResult,
)
from services.validator import run_all_validations
from database.db import init_db


@pytest.fixture(scope="module")
def test_db(tmp_path_factory):
    fn = tmp_path_factory.mktemp("data") / "test_val.db"
    db_path = str(fn)
    init_db(db_path=db_path, force_reseed=True)
    return db_path


def test_missing_required_fields_fails(test_db):
    ext = ExtractedInvoice(
        vendor_name="Apex Cloud Solutions LLC",
        invoice_number=None,  # Missing
        invoice_date=date(2026, 2, 1),
        total_amount=Decimal("500.00"),
    )
    po_res = POMatchResult(is_matched=True, po_number="PO-2026-101", within_tolerance=True)
    checks = run_all_validations(ext, {}, po_res, "dummy_hash_1", db_path=test_db)

    req_check = next(c for c in checks if c.check_name == "REQUIRED_FIELDS")
    assert req_check.status == CheckStatus.FAIL
    assert req_check.is_blocking is True
    assert "Invoice Number" in req_check.actual


def test_arithmetic_consistency_check(test_db):
    # Pass case
    ext_pass = ExtractedInvoice(
        vendor_name="Apex Cloud Solutions LLC",
        invoice_number="INV-100",
        invoice_date=date(2026, 2, 1),
        subtotal=Decimal("100.00"),
        tax_amount=Decimal("8.50"),
        total_amount=Decimal("108.50"),
    )
    po_res = POMatchResult(is_matched=True, po_number="PO-2026-101", within_tolerance=True)
    checks_pass = run_all_validations(ext_pass, {}, po_res, "hash_pass", db_path=test_db)
    arith_check = next(c for c in checks_pass if c.check_name == "ARITHMETIC_HEADER_CONSISTENCY")
    assert arith_check.status == CheckStatus.PASS

    # Fail case
    ext_fail = ExtractedInvoice(
        vendor_name="Apex Cloud Solutions LLC",
        invoice_number="INV-101",
        invoice_date=date(2026, 2, 1),
        subtotal=Decimal("100.00"),
        tax_amount=Decimal("8.50"),
        total_amount=Decimal("150.00"),  # Mismatch
    )
    checks_fail = run_all_validations(ext_fail, {}, po_res, "hash_fail", db_path=test_db)
    arith_fail = next(c for c in checks_fail if c.check_name == "ARITHMETIC_HEADER_CONSISTENCY")
    assert arith_fail.status == CheckStatus.FAIL


def test_vendor_approval_statuses(test_db):
    po_res = POMatchResult(is_matched=True, po_number="PO-2026-101", within_tolerance=True)

    # 1. Approved vendor
    ext_appr = ExtractedInvoice(vendor_name="Apex Cloud Solutions LLC", invoice_number="INV-1", invoice_date=date(2026, 2, 1), total_amount=Decimal("100"))
    checks1 = run_all_validations(ext_appr, {}, po_res, "h1", db_path=test_db)
    v_check1 = next(c for c in checks1 if c.check_name == "VENDOR_APPROVAL_STATUS")
    assert v_check1.status == CheckStatus.PASS

    # 2. Blocked vendor
    ext_blk = ExtractedInvoice(vendor_name="Blacklisted Supply Co.", invoice_number="INV-2", invoice_date=date(2026, 2, 1), total_amount=Decimal("100"))
    checks2 = run_all_validations(ext_blk, {}, po_res, "h2", db_path=test_db)
    v_check2 = next(c for c in checks2 if c.check_name == "VENDOR_APPROVAL_STATUS")
    assert v_check2.status == CheckStatus.FAIL
    assert v_check2.is_blocking is True

    # 3. Pending Review vendor
    ext_pend = ExtractedInvoice(vendor_name="Vanguard Cyber Defense Ltd", invoice_number="INV-3", invoice_date=date(2026, 2, 1), total_amount=Decimal("100"))
    checks3 = run_all_validations(ext_pend, {}, po_res, "h3", db_path=test_db)
    v_check3 = next(c for c in checks3 if c.check_name == "VENDOR_APPROVAL_STATUS")
    assert v_check3.status == CheckStatus.FAIL
    assert v_check3.is_blocking is False  # Pending routes to review, not hard block
