# Zamp AI Solutions Analyst — Assignment Requirements
## Problem Statement 1: Invoice Processing — From PDF to Decision

### 1. Executive Summary & Context
A mid-size enterprise accounts payable (AP) team receives hundreds of vendor invoices monthly via email as PDF documents. The legacy manual workflow involves:
1. Opening incoming invoice PDFs.
2. Manually extracting invoice metadata (vendor, invoice #, dates, line items, subtotals, tax, and total amount).
3. Cross-referencing procurement records to find the matching purchase order (PO).
4. Verifying vendor approval status, checking for duplicate submissions, confirming unit prices, quantities, arithmetic, and applying tolerance rules.
5. Determining invoice disposition: **Eligible for Approval**, **Manual Review**, or **On Hold**.
6. Documenting a clear audit trail and business rationale for every decision.

Manual processing creates operational bottlenecks, slow cycle times, high error rates on complex edge cases, and vulnerability to duplicate or fraudulent payments.

---

### 2. Assignment Deliverables & Criteria
As specified in the candidate guide (`asa-case-study-candidate.pdf`):
- **Deliverable 1: Live Runnable Process**: An automated process that actually executes on real inputs (PDF invoices), runs modular workflow stages, and produces structured, explainable decisions. Accompanied by a Streamlit UI featuring a **Live Run View** (stage-by-stage execution) and a **Dashboard** (metrics, history, filters, audit logs).
- **Deliverable 2: 5-Minute Demo Video Walkthrough**: Prepared demo sequence covering happy path and all 4 edge cases with business narration.
- **Deliverable 3: Live Interview Readiness**: Real-time execution without static mockups or fake stubs.

---

### 3. Workflow Stages
The end-to-end automated pipeline consists of 8 explicit stages:
1. **Stage 1 — Ingestion**: Validate file type (.pdf) and size (<10MB); compute SHA-256 hash; record metadata; enforce idempotency and safe file handling.
2. **Stage 2 — Document Extraction**: Extract raw text via PyMuPDF; detect scanned/low-text PDFs; trigger optional OCR (pytesseract) with graceful fallbacks; perform AI/structured extraction against a strict Pydantic schema (`vendor_name`, `invoice_number`, `invoice_date`, `currency`, `po_reference`, `line_items`, `subtotal`, `tax_amount`, `total_amount`); record confidence and warnings; operate 100% offline in Demo Mode without requiring external API keys.
3. **Stage 3 — Normalization**: Normalize whitespaces, vendor names (conservative legal-entity matching), date formats (ISO 8601 `YYYY-MM-DD`), and currencies (`USD`, `EUR`, `GBP`); preserve raw values alongside normalized tokens.
4. **Stage 4 — Validation**: Deterministic checks for required fields, arithmetic consistency (`subtotal + tax == total`), line-item sum consistency, reasonable date thresholds, vendor existence and approval status, duplicate fingerprints, PO matching confidence, and currency match.
5. **Stage 5 — Purchase-Order Matching**: Match against procurement database using PO reference, vendor legal identity, currency, and line items. Check cumulative consumption against remaining PO balance; calculate absolute and percentage variances; support partial invoicing.
6. **Stage 6 — Decision Engine**: Deterministic rules engine with documented precedence:
   - `ON_HOLD`: Blocking violations (confirmed duplicate, unapproved/blocked vendor, fatal arithmetic corruption).
   - `REVIEW_REQUIRED`: Material amount discrepancies exceeding tolerance, partial PO balance exhaustion, missing critical fields, low OCR/extraction confidence, or ambiguous PO match.
   - `APPROVAL_ELIGIBLE`: Approved vendor, valid non-duplicate invoice, all arithmetic checks valid, matching PO found, total within tolerance ($50 or 2% whichever is smaller).
7. **Stage 7 — Persistence & Audit**: Complete SQLite transaction recording raw metadata, extracted schema, validation test results, matched PO details, remaining balance delta, decision reason hierarchy, and timestamp.
8. **Stage 8 — Results & Presentation**: Rich UI representation with clear status badges, audit breakdown, side-by-side PO comparison, and AP reviewer action recommendations.

---

### 4. Edge Cases Specification
1. **Edge Case 1 — Duplicate Invoice Submission**:
   - Re-upload of an identical or slightly altered PDF with the same vendor + invoice number + amount, or identical file hash.
   - Expected behavior: Detected idempotently; existing record identified; placed `ON_HOLD`; no duplicate PO balance consumption.
2. **Edge Case 2 — Multiple Invoices Against Single PO (Split PO / Cumulative Balance Overdraft)**:
   - Legitimate partial invoices against one PO (e.g. Milestone 1 and Milestone 2).
   - Expected behavior: First invoice reduces PO balance cleanly. Second invoice consumes remaining balance. A third invoice exceeding the remaining balance is flagged as `REVIEW_REQUIRED` (exceeds remaining balance) without double-counting on retries.
3. **Edge Case 3 — Amount Discrepancy & Tolerance Boundary**:
   - Invoice total differs from PO total.
   - Configured tolerance: Within $50.00 or 2.0% variance -> `APPROVAL_ELIGIBLE` with variance warning. Beyond tolerance -> `REVIEW_REQUIRED` with clear delta ($ and %) and line item comparison.
4. **Edge Case 4 — Missing or Unreliable Data (Scanned / Degraded Document)**:
   - Scanned invoice image or missing critical invoice number/date/total.
   - Expected behavior: OCR attempt; critical missing fields explicitly flagged; no hallucinated values; routed to `REVIEW_REQUIRED` or `ON_HOLD` with suggested next AP actions.
