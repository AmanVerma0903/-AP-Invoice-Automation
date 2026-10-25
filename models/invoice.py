"""Pydantic data models for Zamp AP Invoice Automation."""

from decimal import Decimal
from enum import Enum
from typing import List, Optional, Dict, Any
from datetime import date, datetime
from pydantic import BaseModel, Field, field_validator


class DecisionStatus(str, Enum):
    APPROVAL_ELIGIBLE = "APPROVAL_ELIGIBLE"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    ON_HOLD = "ON_HOLD"
    FAILED = "FAILED"

    @property
    def display_label(self) -> str:
        mapping = {
            DecisionStatus.APPROVAL_ELIGIBLE: "Eligible for Approval",
            DecisionStatus.REVIEW_REQUIRED: "Manual Review",
            DecisionStatus.ON_HOLD: "On Hold",
            DecisionStatus.FAILED: "Processing Failed",
        }
        return mapping.get(self, self.value)

    @property
    def badge_color(self) -> str:
        mapping = {
            DecisionStatus.APPROVAL_ELIGIBLE: "#10b981",  # Emerald Green
            DecisionStatus.REVIEW_REQUIRED: "#f59e0b",   # Amber / Orange
            DecisionStatus.ON_HOLD: "#ef4444",           # Rose / Red
            DecisionStatus.FAILED: "#6b7280",            # Gray
        }
        return mapping.get(self, "#6b7280")


class VendorApprovalStatus(str, Enum):
    APPROVED = "APPROVED"
    PENDING_REVIEW = "PENDING_REVIEW"
    BLOCKED = "BLOCKED"
    NOT_FOUND = "NOT_FOUND"


class CheckStatus(str, Enum):
    PASS = "PASS"
    WARN = "WARN"
    FAIL = "FAIL"


class LineItem(BaseModel):
    description: str = Field(..., description="Description of product or service")
    quantity: Optional[Decimal] = Field(default=None, description="Quantity delivered or invoiced")
    unit_price: Optional[Decimal] = Field(default=None, description="Unit price per item")
    amount: Decimal = Field(..., description="Total line amount")

    @field_validator("quantity", "unit_price", "amount", mode="before")
    @classmethod
    def parse_decimal(cls, v):
        if v is None:
            return None
        if isinstance(v, (int, float, str)):
            import re
            cleaned = re.sub(r"[₹\$\€\£]|inr|rs\.?", "", str(v), flags=re.IGNORECASE).replace(",", "").strip()
            if cleaned == "" or cleaned.lower() == "none":
                return None
            return Decimal(cleaned)
        return v


class ExtractedInvoice(BaseModel):
    document_type: Optional[str] = Field(default="Invoice", description="Detected document type (e.g. Tax Invoice, Bill of Supply, Commercial Invoice)")
    vendor_name: Optional[str] = Field(default=None, description="Name of the billing vendor")
    vendor_tax_id: Optional[str] = Field(default=None, description="Tax ID or VAT number of vendor")
    gstin: Optional[str] = Field(default=None, description="GST registration number if applicable")
    pan: Optional[str] = Field(default=None, description="PAN number if applicable")
    invoice_number: Optional[str] = Field(default=None, description="Unique invoice identifier")
    order_number: Optional[str] = Field(default=None, description="Sales or e-commerce order number")
    invoice_date: Optional[date] = Field(default=None, description="Date the invoice was issued")
    due_date: Optional[date] = Field(default=None, description="Payment due date")
    currency: Optional[str] = Field(default="USD", description="Currency symbol or 3-letter code")
    po_reference: Optional[str] = Field(default=None, description="Referenced purchase order number")
    line_items: List[LineItem] = Field(default_factory=list, description="Extracted line items")
    subtotal: Optional[Decimal] = Field(default=None, description="Subtotal before taxes")
    tax_amount: Optional[Decimal] = Field(default=None, description="Total tax or VAT amount")
    tax_breakdown: Dict[str, Decimal] = Field(default_factory=dict, description="Itemized tax components (IGST, CGST, SGST, VAT)")
    total_amount: Optional[Decimal] = Field(default=None, description="Total amount due")
    amount_payable: Optional[Decimal] = Field(default=None, description="Net amount payable if distinct from total")
    extraction_method: str = Field(default="local_heuristic", description="Method used: Gemini model or Local fallback")
    extraction_confidence: float = Field(default=1.0, description="Overall confidence score from 0.0 to 1.0")
    extraction_warnings: List[str] = Field(default_factory=list, description="Warnings generated during extraction")
    page_references: List[int] = Field(default_factory=list, description="Page numbers in source PDF")
    field_evidence: Dict[str, str] = Field(default_factory=dict, description="Evidence snippets for extracted fields")
    raw_text: Optional[str] = Field(default=None, description="Raw extracted text for audit trail")
    sub_invoices: List["ExtractedInvoice"] = Field(default_factory=list, description="Distinct separate documents found in same PDF")

    @field_validator("subtotal", "tax_amount", "total_amount", "amount_payable", mode="before")
    @classmethod
    def parse_financial_amount(cls, v):
        if v is None:
            return None
        if isinstance(v, (int, float, str)):
            import re
            cleaned = re.sub(r"[₹\$\€\£]|inr|rs\.?", "", str(v), flags=re.IGNORECASE).replace(",", "").strip()
            if cleaned == "" or cleaned.lower() == "none":
                return None
            return Decimal(cleaned)
        return v


class ValidationCheck(BaseModel):
    check_name: str
    status: CheckStatus
    expected: Optional[str] = None
    actual: Optional[str] = None
    message: str
    is_blocking: bool = False


class POMatchResult(BaseModel):
    po_number: Optional[str] = None
    vendor_id: Optional[str] = None
    matched_vendor_name: Optional[str] = None
    match_confidence: float = 0.0
    is_matched: bool = False
    po_total: Optional[Decimal] = None
    po_remaining_balance: Optional[Decimal] = None
    po_currency: Optional[str] = None
    po_status: Optional[str] = None
    amount_variance: Optional[Decimal] = None
    percentage_variance: Optional[float] = None
    within_tolerance: bool = False
    tolerance_threshold_used: Optional[Decimal] = None
    exceeds_remaining_balance: bool = False
    is_partial_invoice: bool = False
    explanation: str = ""


class DecisionResult(BaseModel):
    status: DecisionStatus
    display_label: str
    primary_reason: str
    all_reasons: List[str]
    suggested_actions: List[str]
    confidence_score: float = 1.0
    tolerance_applied: Optional[Dict[str, Any]] = None


class CompleteProcessingResult(BaseModel):
    invoice_id: str
    file_name: str
    file_hash: str
    processing_timestamp: datetime
    extracted_data: ExtractedInvoice
    normalized_data: Dict[str, Any]
    validation_checks: List[ValidationCheck]
    po_match: POMatchResult
    decision: DecisionResult
    audit_events: List[Dict[str, Any]]
    sub_results: List["CompleteProcessingResult"] = Field(default_factory=list, description="Results for subdocuments in multi-document PDF")

