"""Unit tests for Pydantic models and normalization utilities."""

from decimal import Decimal
from datetime import date
import pytest
from models.invoice import (
    LineItem,
    ExtractedInvoice,
    DecisionStatus,
    CheckStatus,
    ValidationCheck,
    POMatchResult,
    DecisionResult,
)
from services.normalizer import (
    normalize_vendor_name,
    normalize_date,
    normalize_currency,
    to_decimal,
)


def test_line_item_decimal_parsing():
    item = LineItem(
        description="Hosting Service",
        quantity="2",
        unit_price="$1,500.50",
        amount="$3,001.00",
    )
    assert item.quantity == Decimal("2")
    assert item.unit_price == Decimal("1500.50")
    assert item.amount == Decimal("3001.00")


def test_extracted_invoice_defaults():
    inv = ExtractedInvoice()
    assert inv.vendor_name is None
    assert inv.invoice_number is None
    assert inv.currency == "USD"
    assert inv.line_items == []
    assert inv.total_amount is None


def test_decision_status_display_labels():
    assert DecisionStatus.APPROVAL_ELIGIBLE.display_label == "Eligible for Approval"
    assert DecisionStatus.REVIEW_REQUIRED.display_label == "Manual Review"
    assert DecisionStatus.ON_HOLD.display_label == "On Hold"


def test_normalize_vendor_name():
    assert normalize_vendor_name("Apex Cloud Solutions, LLC") == "apex cloud solutions"
    assert normalize_vendor_name("Datacore Infrastructure Inc.") == "datacore infrastructure"
    assert normalize_vendor_name("Vanguard Cyber Defense Ltd.") == "vanguard cyber defense"
    assert normalize_vendor_name("EuroTech Consulting SAS") == "eurotech consulting"
    assert normalize_vendor_name("   ACME CORP.  ") == "acme"


def test_normalize_date():
    assert normalize_date("2026-02-15") == date(2026, 2, 15)
    assert normalize_date("02/15/2026") == date(2026, 2, 15)
    assert normalize_date("February 15, 2026") == date(2026, 2, 15)
    assert normalize_date(None) is None
    assert normalize_date("invalid-date-string") is None


def test_normalize_currency():
    assert normalize_currency("$") == "USD"
    assert normalize_currency("USD") == "USD"
    assert normalize_currency("€") == "EUR"
    assert normalize_currency("EUR") == "EUR"
    assert normalize_currency("£") == "GBP"
    assert normalize_currency(None) == "USD"


def test_to_decimal():
    assert to_decimal("$1,234.56") == Decimal("1234.56")
    assert to_decimal("€500.00") == Decimal("500.00")
    assert to_decimal(100) == Decimal("100.00")
    assert to_decimal(None) is None
