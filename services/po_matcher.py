"""Purchase Order matching, balance consumption tracking, and tolerance calculations."""

import json
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, Any, Optional, Tuple

from models.invoice import ExtractedInvoice, POMatchResult
from database.db import find_po_by_number, find_pos_for_vendor, find_vendor_by_name

# Configurable tolerance policy: min($50.00, 2.0% of PO Total)
DEFAULT_MAX_ABS_TOLERANCE = Decimal("50.00")
DEFAULT_MAX_PCT_TOLERANCE = Decimal("0.02")  # 2.0%


def calculate_tolerance_limit(po_total: Decimal) -> Decimal:
    """Calculate the maximum allowable dollar discrepancy for a given PO total."""
    pct_limit = (po_total * DEFAULT_MAX_PCT_TOLERANCE).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return min(DEFAULT_MAX_ABS_TOLERANCE, pct_limit)


def match_purchase_order(
    extracted: ExtractedInvoice,
    normalized: Dict[str, Any],
    db_path: Optional[str] = None,
) -> POMatchResult:
    """Match extracted invoice against procurement records and evaluate balance/tolerance."""
    po_ref = extracted.po_reference
    vendor_name = extracted.vendor_name
    inv_total = extracted.total_amount
    inv_curr = normalized.get("normalized_currency", "USD")

    # 1. Lookup Vendor in Master Records
    vendor_row = find_vendor_by_name(vendor_name, db_path=db_path) if vendor_name else None
    vendor_id = vendor_row["vendor_id"] if vendor_row else None
    matched_vname = vendor_row["name"] if vendor_row else None

    # 2. Direct PO Lookup if reference exists
    po_row = None
    if po_ref:
        po_row = find_po_by_number(po_ref, db_path=db_path)

    # 3. Fallback matching if no PO reference on invoice but vendor is known
    if not po_row and vendor_id and inv_total:
        candidate_pos = find_pos_for_vendor(vendor_id, db_path=db_path)
        for cand in candidate_pos:
            cand_bal = Decimal(str(cand["remaining_balance"]))
            cand_tot = Decimal(str(cand["total_amount"]))
            # Match if remaining balance or total is within tolerance of invoice total
            if abs(cand_bal - inv_total) <= DEFAULT_MAX_ABS_TOLERANCE or abs(cand_tot - inv_total) <= DEFAULT_MAX_ABS_TOLERANCE:
                po_row = cand
                break

    # If still no PO found
    if not po_row:
        if po_ref:
            explanation = f"No matching purchase order found for reference '{po_ref}' and vendor '{vendor_name or 'Unknown'}'. Procurement PO verification is required."
        elif extracted.order_number:
            explanation = f"No corporate Purchase Order referenced on invoice (detected Sales Order #: {extracted.order_number}). Vendor '{vendor_name or 'Unknown'}' requires an approved corporate PO. Procurement PO is required."
        else:
            explanation = f"No corporate Purchase Order referenced on invoice for vendor '{vendor_name or 'Unknown'}'. Procurement PO is required."

        return POMatchResult(
            po_number=po_ref,
            vendor_id=vendor_id,
            matched_vendor_name=matched_vname,
            match_confidence=0.0,
            is_matched=False,
            explanation=explanation,
        )

    # PO Found - extract figures
    po_num = po_row["po_number"]
    po_vendor_id = po_row["vendor_id"]
    po_total = Decimal(str(po_row["total_amount"]))
    po_rem_bal = Decimal(str(po_row["remaining_balance"]))
    po_curr = po_row.get("currency", "USD")
    po_status = po_row.get("status", "OPEN")

    # Check vendor consistency
    if vendor_id and po_vendor_id != vendor_id:
        return POMatchResult(
            po_number=po_num,
            vendor_id=vendor_id,
            matched_vendor_name=matched_vname,
            match_confidence=0.3,
            is_matched=False,
            po_total=po_total,
            po_remaining_balance=po_rem_bal,
            po_currency=po_curr,
            po_status=po_status,
            explanation=f"PO {po_num} belongs to vendor '{po_vendor_id}', but invoice was issued by '{vendor_id}'. Vendor mismatch.",
        )

    # Check currency consistency
    if inv_curr and po_curr and inv_curr != po_curr:
        return POMatchResult(
            po_number=po_num,
            vendor_id=vendor_id,
            matched_vendor_name=matched_vname,
            match_confidence=0.5,
            is_matched=False,
            po_total=po_total,
            po_remaining_balance=po_rem_bal,
            po_currency=po_curr,
            po_status=po_status,
            explanation=f"Currency mismatch: Invoice is in {inv_curr}, while PO {po_num} is denominated in {po_curr}.",
        )

    # If invoice total is missing
    if inv_total is None:
        return POMatchResult(
            po_number=po_num,
            vendor_id=vendor_id,
            matched_vendor_name=matched_vname,
            match_confidence=0.6,
            is_matched=True,
            po_total=po_total,
            po_remaining_balance=po_rem_bal,
            po_currency=po_curr,
            po_status=po_status,
            explanation=f"PO {po_num} matched, but invoice total is missing. Cannot verify amounts.",
        )

    # Calculate Variances and Balances
    tolerance_limit = calculate_tolerance_limit(po_total)
    amt_variance = (inv_total - po_total).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    abs_variance = abs(amt_variance)
    pct_variance = float(round((abs_variance / po_total) * 100, 2)) if po_total > 0 else 0.0

    exceeds_remaining = inv_total > (po_rem_bal + tolerance_limit)
    within_tolerance = (abs_variance <= tolerance_limit) and not exceeds_remaining
    is_partial = (inv_total < po_total) and (abs_variance > tolerance_limit) and not exceeds_remaining

    explanation_parts = []
    if exceeds_remaining:
        explanation_parts.append(
            f"Invoice total (${inv_total:,.2f}) exceeds remaining unbilled PO balance (${po_rem_bal:,.2f}). "
            f"Original PO Total: ${po_total:,.2f}."
        )
    elif is_partial:
        explanation_parts.append(
            f"Partial invoice (${inv_total:,.2f}) against PO total (${po_total:,.2f}). "
            f"Sufficient remaining balance available (${po_rem_bal:,.2f})."
        )
    elif within_tolerance:
        if abs_variance == Decimal("0.00"):
            explanation_parts.append(f"Invoice amount (${inv_total:,.2f}) matches PO {po_num} exactly.")
        else:
            explanation_parts.append(
                f"Invoice amount (${inv_total:,.2f}) differs by ${abs_variance:,.2f} ({pct_variance}%) from PO {po_num} (${po_total:,.2f}), "
                f"which is within allowable tolerance (${tolerance_limit:,.2f})."
            )
    else:
        # Exceeds tolerance
        explanation_parts.append(
            f"Invoice total (${inv_total:,.2f}) differs from PO {po_num} (${po_total:,.2f}) by ${abs_variance:,.2f} ({pct_variance}%), "
            f"exceeding allowable tolerance (${tolerance_limit:,.2f})."
        )

    return POMatchResult(
        po_number=po_num,
        vendor_id=vendor_id,
        matched_vendor_name=matched_vname,
        match_confidence=1.0 if (within_tolerance or is_partial) else 0.7,
        is_matched=True,
        po_total=po_total,
        po_remaining_balance=po_rem_bal,
        po_currency=po_curr,
        po_status=po_status,
        amount_variance=amt_variance,
        percentage_variance=pct_variance,
        within_tolerance=within_tolerance,
        tolerance_threshold_used=tolerance_limit,
        exceeds_remaining_balance=exceeds_remaining,
        is_partial_invoice=is_partial,
        explanation=" ".join(explanation_parts),
    )
