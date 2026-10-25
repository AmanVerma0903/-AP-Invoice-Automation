"""Deterministic validation checks for accounts payable invoices."""

from decimal import Decimal
from datetime import date, timedelta
from typing import List, Dict, Any, Optional

from models.invoice import (
    ExtractedInvoice,
    ValidationCheck,
    CheckStatus,
    POMatchResult,
    VendorApprovalStatus,
)
from database.db import (
    check_duplicate_file_hash,
    check_duplicate_invoice_number,
    check_content_duplicate,
    find_vendor_by_name,
)


def run_all_validations(
    extracted: ExtractedInvoice,
    normalized: Dict[str, Any],
    po_match: POMatchResult,
    file_hash: str,
    db_path: Optional[str] = None,
) -> List[ValidationCheck]:
    """Execute all deterministic financial, procurement, and data validations."""
    checks: List[ValidationCheck] = []

    # 1. Check: Duplicate File Hash
    dup_file = check_duplicate_file_hash(file_hash, db_path=db_path) if file_hash else None
    if dup_file:
        checks.append(ValidationCheck(
            check_name="DUPLICATE_FILE_CHECK",
            status=CheckStatus.FAIL,
            is_blocking=True,
            expected="Unique document file hash",
            actual=f"Matches invoice '{dup_file['id']}' ({dup_file['file_name']})",
            message=f"Duplicate file uploaded. Exactly matches existing processed invoice {dup_file.get('invoice_number', 'N/A')} from {dup_file.get('created_at', '')[:10]}.",
        ))
    else:
        checks.append(ValidationCheck(
            check_name="DUPLICATE_FILE_CHECK",
            status=CheckStatus.PASS,
            expected="Unique document file hash",
            actual="Verified unique",
            message="File SHA-256 hash is unique in invoice repository.",
        ))

    # 2. Check: Duplicate Invoice Identifier (Vendor + Invoice Number)
    vname = extracted.vendor_name
    inv_num = extracted.invoice_number
    if vname and inv_num:
        dup_inv = check_duplicate_invoice_number(vname, inv_num, db_path=db_path)
        if dup_inv:
            checks.append(ValidationCheck(
                check_name="DUPLICATE_INVOICE_NUMBER",
                status=CheckStatus.FAIL,
                is_blocking=True,
                expected="Unique invoice number for vendor",
                actual=f"Matches invoice '{dup_inv['id']}' ({dup_inv['invoice_number']})",
                message=f"Duplicate invoice detected. Vendor '{vname}' already submitted invoice number '{inv_num}' on {dup_inv.get('created_at', '')[:10]}.",
            ))
        else:
            checks.append(ValidationCheck(
                check_name="DUPLICATE_INVOICE_NUMBER",
                status=CheckStatus.PASS,
                expected="Unique invoice number for vendor",
                actual=f"Unique: {inv_num}",
                message="Invoice number has not been previously recorded for this vendor.",
            ))

    # 3. Check: Required Fields
    missing_required = []
    if not extracted.vendor_name:
        missing_required.append("Vendor Name")
    if not extracted.invoice_number:
        missing_required.append("Invoice Number")
    if not extracted.invoice_date:
        missing_required.append("Invoice Date")
    if extracted.total_amount is None:
        missing_required.append("Total Amount")

    if missing_required:
        is_blocking = "Invoice Number" in missing_required or "Vendor Name" in missing_required
        checks.append(ValidationCheck(
            check_name="REQUIRED_FIELDS",
            status=CheckStatus.FAIL,
            is_blocking=is_blocking,
            expected="Vendor Name, Invoice Number, Invoice Date, Total Amount",
            actual=f"Missing: {', '.join(missing_required)}",
            message=f"Mandatory invoice fields are missing: {', '.join(missing_required)}.",
        ))
    else:
        checks.append(ValidationCheck(
            check_name="REQUIRED_FIELDS",
            status=CheckStatus.PASS,
            expected="All 4 core mandatory fields present",
            actual="All present",
            message="All core mandatory invoice fields successfully extracted.",
        ))

    # 4. Check: Vendor Master & Approval Status
    if vname:
        from services.llm_extractor import is_invalid_vendor_candidate
        if is_invalid_vendor_candidate(vname):
            checks.append(ValidationCheck(
                check_name="VENDOR_IDENTITY_VALIDATION",
                status=CheckStatus.FAIL,
                is_blocking=False,
                expected="Valid legal entity seller/vendor name",
                actual=vname,
                message=f"Extracted vendor string '{vname}' appears to be a document header or invalid entity. Vendor identity requires verification.",
            ))

        vendor_row = find_vendor_by_name(vname, db_path=db_path)
        if not vendor_row:
            checks.append(ValidationCheck(
                check_name="VENDOR_APPROVAL_STATUS",
                status=CheckStatus.FAIL,
                is_blocking=False,  # Unlisted vendor triggers Manual Review, not a payment freeze
                expected="Approved Vendor in Master Procurement Records",
                actual="Unregistered / New Vendor",
                message=f"Vendor '{vname}' is not currently in the approved procurement vendor database. Requires AP onboarding verification.",
            ))
        else:
            v_status = vendor_row["approval_status"]
            if v_status == "APPROVED":
                checks.append(ValidationCheck(
                    check_name="VENDOR_APPROVAL_STATUS",
                    status=CheckStatus.PASS,
                    expected="APPROVED",
                    actual="APPROVED",
                    message=f"Vendor '{vendor_row['name']}' ({vendor_row['vendor_id']}) is approved for payment.",
                ))
            elif v_status == "BLOCKED":
                checks.append(ValidationCheck(
                    check_name="VENDOR_APPROVAL_STATUS",
                    status=CheckStatus.FAIL,
                    is_blocking=True,  # Payment freeze on confirmed BLOCKED vendors
                    expected="APPROVED",
                    actual="BLOCKED",
                    message=f"Vendor '{vendor_row['name']}' is on payment freeze / BLOCKED status in procurement system.",
                ))
            else:  # PENDING_REVIEW
                checks.append(ValidationCheck(
                    check_name="VENDOR_APPROVAL_STATUS",
                    status=CheckStatus.FAIL,
                    is_blocking=False,
                    expected="APPROVED",
                    actual="PENDING_REVIEW",
                    message=f"Vendor '{vendor_row['name']}' onboarding is PENDING_REVIEW. Verification required before release.",
                ))

    # 5. Check: Subtotal + Tax = Total Arithmetic Consistency
    subtotal = extracted.subtotal
    tax = extracted.tax_amount
    total = extracted.total_amount
    if subtotal is not None and tax is not None and total is not None:
        computed_total = subtotal + tax
        delta = abs(computed_total - total)
        if delta <= Decimal("0.05"):
            checks.append(ValidationCheck(
                check_name="ARITHMETIC_HEADER_CONSISTENCY",
                status=CheckStatus.PASS,
                expected=f"${total:,.2f}",
                actual=f"Subtotal (${subtotal:,.2f}) + Tax (${tax:,.2f}) = ${computed_total:,.2f}",
                message="Header arithmetic reconciled: Subtotal + Tax equals Invoice Total.",
            ))
        else:
            checks.append(ValidationCheck(
                check_name="ARITHMETIC_HEADER_CONSISTENCY",
                status=CheckStatus.FAIL,
                is_blocking=False,
                expected=f"${total:,.2f}",
                actual=f"${computed_total:,.2f} (diff ${delta:,.2f})",
                message=f"Arithmetic mismatch: Subtotal (${subtotal:,.2f}) + Tax (${tax:,.2f}) != Total (${total:,.2f}).",
            ))

    # 6. Check: Line Items Sum Consistency
    if extracted.line_items and subtotal is not None:
        items_sum = sum(item.amount for item in extracted.line_items)
        items_delta = abs(items_sum - subtotal)
        if items_delta <= Decimal("0.05"):
            checks.append(ValidationCheck(
                check_name="LINE_ITEMS_SUM_CONSISTENCY",
                status=CheckStatus.PASS,
                expected=f"Subtotal: ${subtotal:,.2f}",
                actual=f"Sum of {len(extracted.line_items)} line items: ${items_sum:,.2f}",
                message="Line item amounts reconcile with invoice subtotal.",
            ))
        else:
            checks.append(ValidationCheck(
                check_name="LINE_ITEMS_SUM_CONSISTENCY",
                status=CheckStatus.WARN,
                expected=f"Subtotal: ${subtotal:,.2f}",
                actual=f"Sum: ${items_sum:,.2f} (diff ${items_delta:,.2f})",
                message=f"Line item sum (${items_sum:,.2f}) does not match subtotal (${subtotal:,.2f}).",
            ))

    # 7. Check: Reasonable Invoice Date
    if extracted.invoice_date:
        today = date.today()
        # Future date check (> 7 days in future)
        if extracted.invoice_date > (today + timedelta(days=7)):
            checks.append(ValidationCheck(
                check_name="INVOICE_DATE_PLAUSIBILITY",
                status=CheckStatus.WARN,
                expected="Invoice date on or before current date",
                actual=str(extracted.invoice_date),
                message="Invoice date is set in the future.",
            ))
        # Stale invoice check (> 180 days old)
        elif extracted.invoice_date < (today - timedelta(days=180)):
            checks.append(ValidationCheck(
                check_name="INVOICE_DATE_PLAUSIBILITY",
                status=CheckStatus.WARN,
                expected="Invoice issued within past 180 days",
                actual=str(extracted.invoice_date),
                message="Invoice issue date is older than 6 months (stale invoice).",
            ))
        else:
            checks.append(ValidationCheck(
                check_name="INVOICE_DATE_PLAUSIBILITY",
                status=CheckStatus.PASS,
                expected="Recent date within standard AP window",
                actual=str(extracted.invoice_date),
                message="Invoice date is within acceptable operational range.",
            ))

    # 8. Check: Purchase Order Matching & Balance
    if not po_match.is_matched:
        actual_desc = po_match.po_number if po_match.po_number else (
            f"No PO on invoice (Order #: {extracted.order_number})" if extracted.order_number else "No PO Referenced"
        )
        checks.append(ValidationCheck(
            check_name="PURCHASE_ORDER_MATCH",
            status=CheckStatus.FAIL,
            is_blocking=False,
            expected="Valid PO in procurement records",
            actual=actual_desc,
            message=po_match.explanation or "Purchase order reference could not be matched.",
        ))
    else:
        po_tot_str = f"${po_match.po_total:,.2f}" if po_match.po_total is not None else "N/A"
        po_bal_str = f"${po_match.po_remaining_balance:,.2f}" if po_match.po_remaining_balance is not None else "N/A"
        inv_tot_str = f"${extracted.total_amount:,.2f}" if extracted.total_amount is not None else "N/A"
        tol_str = f"${po_match.tolerance_threshold_used:,.2f}" if po_match.tolerance_threshold_used is not None else "$50.00"

        if po_match.exceeds_remaining_balance:
            checks.append(ValidationCheck(
                check_name="PO_BALANCE_SUFFICIENCY",
                status=CheckStatus.FAIL,
                is_blocking=False,
                expected=f"Invoice <= Remaining PO Balance ({po_bal_str})",
                actual=f"Invoice: {inv_tot_str}",
                message=po_match.explanation,
            ))
        elif not po_match.within_tolerance and not po_match.is_partial_invoice:
            checks.append(ValidationCheck(
                check_name="PO_AMOUNT_TOLERANCE",
                status=CheckStatus.FAIL,
                is_blocking=False,
                expected=f"Within tolerance ({tol_str}) of PO ({po_tot_str})",
                actual=f"Variance: ${abs(po_match.amount_variance or 0):,.2f} ({po_match.percentage_variance}%)",
                message=po_match.explanation,
            ))
        else:
            status_val = CheckStatus.WARN if (po_match.amount_variance and abs(po_match.amount_variance) > Decimal("0.01")) else CheckStatus.PASS
            checks.append(ValidationCheck(
                check_name="PURCHASE_ORDER_MATCH",
                status=status_val,
                expected=f"PO {po_match.po_number}",
                actual=f"Matched PO {po_match.po_number} ({po_tot_str})",
                message=po_match.explanation,
            ))

    return checks
