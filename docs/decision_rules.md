# Decision Rules & Tolerance Hierarchy
## Zamp AP Invoice Automation

### 1. Decision Statuses
The automated decision engine categorizes incoming invoices into three business outcomes:

| Internal Status | UI Display Label | Description | Financial Implication |
|---|---|---|---|
| `APPROVAL_ELIGIBLE` | **Eligible for Approval** | All mandatory validations pass, vendor is approved, PO matches, and amounts are within tolerance. | Ready for AP reviewer sign-off or automated batch scheduling. |
| `REVIEW_REQUIRED` | **Manual Review** | Non-blocking exception: tolerance variance, split PO balance overdraft, missing non-critical details, or low extraction confidence. | AP analyst intervention needed to inspect variances or confirm splits. |
| `ON_HOLD` | **On Hold** | Blocking exception: duplicate invoice, blocked or unapproved vendor, fatal arithmetic corruption, or missing required identifiers. | Payment blocked immediately. Requires vendor outreach or re-issuance. |

---

### 2. Decision Precedence Order
When multiple conditions or exceptions occur simultaneously, the engine enforces strict deterministic precedence. A passing check **never** overrides a blocking exception.

```
[Level 1: BLOCKING FAILS -> ON_HOLD]
   ├── Duplicate File Hash or Duplicate Invoice (Vendor + Invoice Number)
   ├── Unapproved or Blocked Vendor
   ├── Corrupted Document / Zero Extracted Content
   └── Fatal Missing Identifiers (Missing Vendor or Missing Invoice Number)
         ↓ (If No Level 1 Violations)
[Level 2: MATERIAL EXCEPTIONS -> REVIEW_REQUIRED]
   ├── Invoice Exceeds Remaining PO Balance (Cumulative Overdraft)
   ├── Amount Mismatch Exceeds Tolerance Threshold
   ├── PO Reference Missing or PO Not Found in Database
   ├── Currency Mismatch (e.g. Invoice EUR vs PO USD)
   ├── Line Item Arithmetic Discrepancy (> $0.05)
   └── Subtotal + Tax != Total (> $0.05)
         ↓ (If No Level 2 Violations)
[Level 3: CLEAN PASS -> APPROVAL_ELIGIBLE]
   ├── Vendor Approved & Active
   ├── Invoice Number & Date Present and Sensible
   ├── PO Found, Open, and Matches Vendor & Currency
   ├── Invoice Total <= Remaining PO Balance
   └── Total Amount Matches PO within Tolerance ($50 or 2%)
```

---

### 3. Detailed Tolerance Policy

In enterprise procurement, small discrepancies (e.g., freight variance, rounding, small tax adjustments) are common. The platform implements a dual-boundary tolerance rule:

- **Absolute Variance Threshold**: `$50.00`
- **Percentage Variance Threshold**: `2.0%` of the Purchase Order total.
- **Allowed Tolerance Limit**: `min($50.00, 0.02 * PO_Total)`

#### Rules:
1. **Zero Discrepancy (`|Invoice - PO| <= $0.01`)**:
   - Status: `APPROVAL_ELIGIBLE`
   - Reason: "Invoice amount matches purchase order exactly."
2. **Permitted Variance (`$0.01 < |Invoice - PO| <= Allowed_Tolerance`)**:
   - Status: `APPROVAL_ELIGIBLE`
   - Reason: "Invoice amount ($X) deviates by $Y (Z%) from PO ($W), which is within the allowable tolerance ($T)."
   - Flag: Informational Warning generated for audit logging.
3. **Material Variance (`|Invoice - PO| > Allowed_Tolerance`)**:
   - Status: `REVIEW_REQUIRED`
   - Reason: "Invoice amount ($X) differs from PO ($W) by $Y (Z%), exceeding the maximum allowable tolerance of $T."
   - Action: Route to AP specialist to verify line items and negotiate credit note.

---

### 4. Edge Cases Handling Matrix

#### Edge Case 1: Duplicate Invoice
- **Trigger**: An invoice with an identical SHA-256 hash OR matching `(vendor_id, invoice_number)`.
- **Precedence**: Level 1 (Blocking).
- **Result**: `ON_HOLD`.
- **Reason**: "Duplicate invoice detected. Matches existing invoice [INV-ID] processed on [DATE]."
- **PO Impact**: Zero consumption. Transaction is aborted before PO balance deduction.

#### Edge Case 2: Multiple Invoices Against Single PO (Cumulative Balance)
- **Scenario**: Vendor issues partial invoice #1 for $4,000 against a $10,000 PO. Balance becomes $6,000.
  - Later, vendor issues invoice #2 for $6,000. Balance becomes $0.00.
  - Subsequently, vendor issues invoice #3 for $2,500.
- **Evaluation**:
  - Invoice #1: Within $10,000 balance -> `APPROVAL_ELIGIBLE`. Remaining balance updated to $6,000.
  - Invoice #2: Within $6,000 balance -> `APPROVAL_ELIGIBLE`. Remaining balance updated to $0.00.
  - Invoice #3: Invoiced amount $2,500 > Remaining balance $0.00 -> `REVIEW_REQUIRED`.
  - Reason: "Invoice amount ($2,500.00) exceeds remaining purchase order balance ($0.00). Original PO: $10,000.00, Previously Invoiced: $10,000.00."

#### Edge Case 3: Amount Discrepancy & Tolerance Boundary
- **Scenario A (Within Tolerance)**:
  - PO total: $5,000.00. Max tolerance: $50.00 (1%).
  - Invoice total: $5,035.00 (+$35.00 / 0.7%).
  - Result: `APPROVAL_ELIGIBLE` with tolerance warning.
- **Scenario B (Material Discrepancy)**:
  - PO total: $5,000.00.
  - Invoice total: $5,450.00 (+$450.00 / 9.0%).
  - Result: `REVIEW_REQUIRED`.
  - Reason: "Invoice total $5,450.00 exceeds PO amount $5,000.00 by $450.00 (+9.00%), surpassing allowable tolerance of $50.00."

#### Edge Case 4: Missing or Unreliable Data (Scanned / Degraded Document)
- **Scenario A (Missing Invoice Number or Vendor)**:
  - Result: `ON_HOLD`.
  - Reason: "Missing critical mandatory fields: Invoice Number. Cannot establish legal payment liability."
  - Suggested Action: Request vendor resubmit a formal legible invoice with standard header fields.
- **Scenario B (Unreadable / Missing Total Amount)**:
  - Result: `REVIEW_REQUIRED` (or `ON_HOLD` if subtotal and line items also missing).
  - Reason: "Unable to extract total payable amount from document. OCR confidence below threshold."
  - Suggested Action: AP reviewer must open PDF in side-by-side viewer and manually enter verified amount.
