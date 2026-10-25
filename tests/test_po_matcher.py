"""Tests for Purchase Order matching, tolerance calculations, and balance tracking."""

import os
from decimal import Decimal
import pytest
from models.invoice import ExtractedInvoice
from services.po_matcher import match_purchase_order, calculate_tolerance_limit
from database.db import init_db


@pytest.fixture(scope="module")
def test_db(tmp_path_factory):
    fn = tmp_path_factory.mktemp("data") / "test_po.db"
    db_path = str(fn)
    init_db(db_path=db_path, force_reseed=True)
    return db_path


def test_calculate_tolerance_limit():
    # 2% of $1,000 is $20 -> limit is min($50, $20) = $20.00
    assert calculate_tolerance_limit(Decimal("1000.00")) == Decimal("20.00")
    # 2% of $5,000 is $100 -> limit is min($50, $100) = $50.00
    assert calculate_tolerance_limit(Decimal("5000.00")) == Decimal("50.00")
    # 2% of $50,000 is $1,000 -> limit capped at $50.00
    assert calculate_tolerance_limit(Decimal("50000.00")) == Decimal("50.00")


def test_exact_po_match(test_db):
    ext = ExtractedInvoice(
        vendor_name="Apex Cloud Solutions LLC",
        po_reference="PO-2026-101",
        total_amount=Decimal("5000.00"),
        currency="USD",
    )
    norm = {"normalized_currency": "USD", "normalized_vendor_name": "apex cloud solutions"}
    res = match_purchase_order(ext, norm, db_path=test_db)

    assert res.is_matched is True
    assert res.po_number == "PO-2026-101"
    assert res.within_tolerance is True
    assert res.amount_variance == Decimal("0.00")
    assert res.exceeds_remaining_balance is False


def test_within_tolerance_match(test_db):
    # PO is $5,000. Invoice is $5,035.00 (+35.00, within $50 tolerance)
    ext = ExtractedInvoice(
        vendor_name="Apex Cloud Solutions LLC",
        po_reference="PO-2026-101",
        total_amount=Decimal("5035.00"),
        currency="USD",
    )
    norm = {"normalized_currency": "USD"}
    res = match_purchase_order(ext, norm, db_path=test_db)

    assert res.is_matched is True
    assert res.within_tolerance is True
    assert res.amount_variance == Decimal("35.00")
    assert res.tolerance_threshold_used == Decimal("50.00")


def test_exceeds_tolerance_match(test_db):
    # PO is $5,000. Invoice is $5,450.00 (+450.00, exceeds $50 tolerance)
    ext = ExtractedInvoice(
        vendor_name="Apex Cloud Solutions LLC",
        po_reference="PO-2026-101",
        total_amount=Decimal("5450.00"),
        currency="USD",
    )
    norm = {"normalized_currency": "USD"}
    res = match_purchase_order(ext, norm, db_path=test_db)

    assert res.is_matched is True
    assert res.within_tolerance is False
    assert res.amount_variance == Decimal("450.00")


def test_partial_invoice_match(test_db):
    # PO-2026-102 total is $12,500.00. Invoice is $5,000.00
    ext = ExtractedInvoice(
        vendor_name="Datacore Infrastructure Inc.",
        po_reference="PO-2026-102",
        total_amount=Decimal("5000.00"),
        currency="USD",
    )
    norm = {"normalized_currency": "USD"}
    res = match_purchase_order(ext, norm, db_path=test_db)

    assert res.is_matched is True
    assert res.is_partial_invoice is True
    assert res.exceeds_remaining_balance is False


def test_currency_mismatch(test_db):
    # Invoice is EUR, PO-2026-101 is USD
    ext = ExtractedInvoice(
        vendor_name="Apex Cloud Solutions LLC",
        po_reference="PO-2026-101",
        total_amount=Decimal("5000.00"),
        currency="EUR",
    )
    norm = {"normalized_currency": "EUR"}
    res = match_purchase_order(ext, norm, db_path=test_db)

    assert res.is_matched is False
    assert "currency mismatch" in res.explanation.lower()
