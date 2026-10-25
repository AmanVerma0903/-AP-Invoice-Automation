"""Deterministic decision engine for Accounts Payable invoice disposition."""

from typing import List, Dict, Any, Optional

from models.invoice import (
    ExtractedInvoice,
    ValidationCheck,
    POMatchResult,
    DecisionResult,
    DecisionStatus,
    CheckStatus,
)


def evaluate_decision(
    extracted: ExtractedInvoice,
    validation_checks: List[ValidationCheck],
    po_match: POMatchResult,
) -> DecisionResult:
    """Evaluate invoice status and synthesize explainable business reasons and next actions.
    
    Decision Precedence:
    1. Blocking Failures -> ON_HOLD
    2. Non-blocking Failures / Variances -> REVIEW_REQUIRED
    3. All Validations Pass -> APPROVAL_ELIGIBLE
    """
    blocking_fails = [c for c in validation_checks if c.status == CheckStatus.FAIL and c.is_blocking]
    non_blocking_fails = [c for c in validation_checks if c.status == CheckStatus.FAIL and not c.is_blocking]
    warnings = [c for c in validation_checks if c.status == CheckStatus.WARN]

    all_reasons: List[str] = []
    suggested_actions: List[str] = []

    # -------------------------------------------------------------
    # LEVEL 1: BLOCKING ISSUES -> ON_HOLD
    # -------------------------------------------------------------
    if blocking_fails:
        # Determine primary reason from blocking failures
        # Prioritize Duplicates, then Vendor Status, then Missing Required
        primary_reason = blocking_fails[0].message
        for c in blocking_fails:
            if "DUPLICATE" in c.check_name:
                primary_reason = c.message
                break
            elif "VENDOR_APPROVAL" in c.check_name:
                primary_reason = c.message

        for c in blocking_fails:
            all_reasons.append(f"[BLOCKING] {c.message}")

        # Add suggested actions based on issues
        if any("DUPLICATE" in c.check_name for c in blocking_fails):
            suggested_actions.append("Reject invoice submission and confirm whether original invoice is already paid or in process.")
            suggested_actions.append("Notify vendor of duplicate submission with prior invoice reference.")
        if any("VENDOR_APPROVAL" in c.check_name for c in blocking_fails):
            suggested_actions.append("Hold payment immediately; vendor is blocked or unapproved in procurement records.")
            suggested_actions.append("Direct vendor to Supplier Onboarding team to resolve compliance / W-9 / banking status.")
        if any("REQUIRED_FIELDS" in c.check_name for c in blocking_fails):
            suggested_actions.append("Contact vendor to request a corrected formal PDF invoice containing all required legal headers.")

        return DecisionResult(
            status=DecisionStatus.ON_HOLD,
            display_label=DecisionStatus.ON_HOLD.display_label,
            primary_reason=primary_reason,
            all_reasons=all_reasons,
            suggested_actions=suggested_actions,
            confidence_score=0.95,
        )

    # -------------------------------------------------------------
    # LEVEL 2: EXCEPTIONS & DISCREPANCIES -> REVIEW_REQUIRED
    # -------------------------------------------------------------
    if non_blocking_fails:
        primary_reason = non_blocking_fails[0].message
        
        # Prioritize PO Overdraft, then Tolerance, then Missing PO
        for c in non_blocking_fails:
            if c.check_name == "PO_BALANCE_SUFFICIENCY":
                primary_reason = c.message
                break
            elif c.check_name == "PO_AMOUNT_TOLERANCE":
                primary_reason = c.message
                break

        for c in non_blocking_fails:
            all_reasons.append(f"[EXCEPTION] {c.message}")
        for w in warnings:
            all_reasons.append(f"[WARNING] {w.message}")

        # Suggested actions
        if not po_match.is_matched:
            if extracted.order_number:
                suggested_actions.append(f"Locate matching corporate PO for e-commerce order {extracted.order_number} or verify expense reimbursement authorization.")
            else:
                suggested_actions.append("Locate relevant PO in procurement ERP or verify if work was authorized under blanket contract.")
        elif po_match.exceeds_remaining_balance:
            suggested_actions.append("Do not approve payment yet: Cumulative invoices exceed total approved purchase order.")
            suggested_actions.append("Request a PO Amendment or Change Order from Procurement/Buyer to increase PO funding.")
        elif not po_match.within_tolerance and not po_match.is_partial_invoice:
            suggested_actions.append(f"Inspect unit prices and quantities against PO line items. Variance exceeds ${po_match.tolerance_threshold_used or 50:.2f}.")
            suggested_actions.append("Request vendor issue a credit memo or provide revised invoice matching agreed PO terms.")

        if any("VENDOR_APPROVAL" in c.check_name for c in non_blocking_fails):
            suggested_actions.append(f"Initiate vendor onboarding review for '{extracted.vendor_name or 'Vendor'}' to verify W-9/tax registration and bank details.")

        if not suggested_actions:
            suggested_actions.append("Review highlighted validation discrepancies before manual sign-off.")

        return DecisionResult(
            status=DecisionStatus.REVIEW_REQUIRED,
            display_label=DecisionStatus.REVIEW_REQUIRED.display_label,
            primary_reason=primary_reason,
            all_reasons=all_reasons,
            suggested_actions=suggested_actions,
            confidence_score=0.85,
            tolerance_applied={
                "threshold": float(po_match.tolerance_threshold_used) if po_match.tolerance_threshold_used else None,
                "amount_variance": float(po_match.amount_variance) if po_match.amount_variance is not None else None,
                "percentage_variance": po_match.percentage_variance,
            },
        )

    # -------------------------------------------------------------
    # LEVEL 3: CLEAN PASS -> APPROVAL_ELIGIBLE
    # -------------------------------------------------------------
    if po_match.is_partial_invoice:
        primary_reason = f"Legitimate partial invoice (${extracted.total_amount:,.2f}) successfully matched to PO {po_match.po_number} with sufficient remaining balance."
    elif po_match.amount_variance and abs(po_match.amount_variance) > 0:
        primary_reason = (
            f"Approved: Invoice amount (${extracted.total_amount:,.2f}) is within configured tolerance "
            f"(${po_match.tolerance_threshold_used:,.2f}) of PO {po_match.po_number}."
        )
    else:
        primary_reason = f"All validations passed: Vendor approved, numbers reconcile, and PO {po_match.po_number} matched exactly."

    all_reasons.append(primary_reason)
    for w in warnings:
        all_reasons.append(f"[WARNING] {w.message}")

    suggested_actions.append("Ready for release: Queue invoice for automated ERP sync and scheduled disbursement batch.")
    suggested_actions.append("Deduct invoiced amount from PO commitment balance.")

    return DecisionResult(
        status=DecisionStatus.APPROVAL_ELIGIBLE,
        display_label=DecisionStatus.APPROVAL_ELIGIBLE.display_label,
        primary_reason=primary_reason,
        all_reasons=all_reasons,
        suggested_actions=suggested_actions,
        confidence_score=extracted.extraction_confidence,
        tolerance_applied={
            "threshold": float(po_match.tolerance_threshold_used) if po_match.tolerance_threshold_used else None,
            "amount_variance": float(po_match.amount_variance) if po_match.amount_variance is not None else None,
            "percentage_variance": po_match.percentage_variance,
        },
    )
