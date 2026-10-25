# 5-Minute Live Demo & Walkthrough Script
## Zamp AI Solutions Analyst — Problem Statement 1: Invoice Processing

### Overview
This demo walkthrough is structured for a 5-minute Loom screen recording and the live interview. It focuses on the actual live execution of the product, transparent explanations of the 8-stage pipeline, and proof of the 4 realistic edge cases.

---

### Step-by-Step Script & Timing (0:00 – 5:00)

#### 0:00 – 0:45: Context & Architectural Overview
- **Visual**: Start on the Streamlit web application with the Executive Header and Dashboard visible.
- **Narration**:
  > *"Hi everyone, today I'm demonstrating an automated Accounts Payable solution built for mid-sized enterprises. In a typical AP team, hundreds of messy PDF invoices arrive every month. Humans spend hours opening PDFs, cross-referencing spreadsheet POs, checking arithmetic, verifying vendor approval status, and tracking remaining balances.
  > 
  > To solve this, I built an end-to-end processing pipeline that takes an invoice PDF and renders an explainable decision: Eligible for Approval, Manual Review, or On Hold. Crucially, I followed enterprise AP best practices: AI is used for structured extraction, but all financial validations, tolerance checks, and decision precedence are 100% deterministic in Python using exact Decimal arithmetic."*

---

#### 0:45 – 1:45: The Happy Path (Clean 1:1 Match)
- **Action**: Go to the **Process Invoice (Live Run)** tab.
- **Action**: Under **Option A: Select Pre-Packaged Scenario Invoice**, select `01_happy_path_apex.pdf (Happy Path: Clean 1:1 Match)`.
- **Action**: Click **🚀 Process Invoice Through Pipeline**.
- **Visual**: Watch the real-time progress bar and stage status cards execute.
- **Narration**:
  > *"Let's run the happy path: an invoice from Apex Cloud Solutions LLC matching Purchase Order PO-2026-101 for $5,000.00.
  > 
  > Notice what happens in real time across the 8 stages:
  > In Stage 1, we validate the file header and calculate a SHA-256 hash.
  > In Stage 2, PyMuPDF extracts the text layer and tabular line items with zero hallucinations.
  > In Stage 3, we normalize dates into ISO-8601 and standardize vendor identity.
  > In Stage 4, we match PO-2026-101 in our procurement SQLite database.
  > In Stage 5, our validation engine verifies that Subtotal ($4,500) + Support ($500) equals Total ($5,000), checks vendor approval, and verifies uniqueness.
  > 
  > The outcome is **Eligible for Approval**. Look at the PO Reconciliation card: the invoice consumed $5,000 from PO-2026-101, reducing its unbilled balance to $0.00 in an ACID transaction."*

---

#### 1:45 – 2:30: Edge Case 1 — Duplicate Invoice Detection
- **Action**: In the dropdown, select `02_duplicate_original_glp.pdf`. Click **Process Invoice**.
  - Show it is **Eligible for Approval** ($8,400.00).
- **Action**: Now select `02_duplicate_resubmission_glp_renamed.pdf`. Click **Process Invoice**.
- **Visual**: Shows **ON HOLD** status banner in Rose with duplicate identification.
- **Narration**:
  > *"Now let's examine Edge Case 1: Duplicate submission. A vendor or colleague often resubmits an invoice weeks later with a modified filename.
  > 
  > Notice how our system behaves: Even though the filename changed from `02_duplicate_original_glp.pdf` to `02_duplicate_resubmission_glp_renamed.pdf`, the system detected the duplicate using a multi-factor check on Vendor identity and Invoice Number INV-GLP-8801.
  > 
  > Precedence Rule Level 1 triggered immediately, placing the invoice **ON HOLD**. Crucially, the transaction was aborted before touching the purchase order, guaranteeing zero double-consumption."*

---

#### 2:30 – 3:30: Edge Case 2 — Multiple Invoices Against One PO (Split PO & Overdraft)
- **Action**: Select `03a_split_po_milestone1_datacore.pdf` ($5,000.00 against $12,500 PO-2026-102).
  - Click **Process Invoice**. Show it is **Eligible for Approval**; remaining balance is now $7,500.00.
- **Action**: Select `03b_split_po_milestone2_datacore.pdf` ($7,500.00).
  - Click **Process Invoice**. Show it is **Eligible for Approval**; remaining balance is now $0.00.
- **Action**: Select `03c_split_po_overdraft_datacore.pdf` ($3,000.00).
  - Click **Process Invoice**.
- **Visual**: Status is **MANUAL REVIEW REQUIRED** in Amber.
- **Narration**:
  > *"Edge Case 2 addresses real-world milestone billing. Datacore Infrastructure has a $12,500 PO.
  > Invoice 1 arrived for Milestone 1 ($5,000) — approved, leaving $7,500 balance.
  > Invoice 2 arrived for Milestone 2 ($7,500) — approved, depleting the balance to $0.00.
  > 
  > Now the vendor submits a 3rd invoice for $3,000 of extra cabling. Notice the engine's reaction: It flags that cumulative invoicing exceeds the remaining PO balance ($0.00) and routes it to **Manual Review**.
  > 
  > Look at the suggested actions: It tells the AP analyst: 'Do not approve payment yet: Cumulative invoices exceed total approved purchase order. Request a PO Change Order from Procurement.'"*

---

#### 3:30 – 4:15: Edge Case 3 — Amount Discrepancy & Tolerance Boundary
- **Action**: Select `04a_within_tolerance_apex.pdf` ($5,035.00 vs $5,000.00 PO).
  - Click **Process Invoice**. Show it is **Eligible for Approval** (variance +$35 is within $50 tolerance).
- **Action**: Select `04b_exceeds_tolerance_apex.pdf` ($5,450.00 vs $5,000.00 PO).
  - Click **Process Invoice**. Show it is **Manual Review** (variance +$450 exceeds $50 tolerance).
- **Narration**:
  > *"Edge Case 3 tests contractual variance. Many vendors include minor shipping overages.
  > Our configured policy permits discrepancies up to $50.00 or 2% of the PO.
  > In invoice 4a ($5,035.00), the $35 difference is within tolerance, so it is approved with an informational audit note.
  > But in invoice 4b ($5,450.00), the $450 discrepancy (+9.0%) exceeds the threshold, routing it to Manual Review and generating a recommended action to request a credit memo."*

---

#### 4:15 – 5:00: Edge Case 4, Audit Ledger & Wrap-up
- **Action**: Select `05_missing_invoice_number_apex.pdf` (Missing invoice number).
  - Click **Process Invoice**. Show it is placed **ON HOLD**, identifying the exact missing field.
- **Action**: Switch to the **🗄️ Audit History & Search** tab and show the filterable table and drill-down audit log.
- **Narration**:
  > *"In Edge Case 4, an invoice is missing its legal invoice number. The system never invents or hallucinates missing data; it places the invoice On Hold and instructs the team to request a compliant invoice.
  > 
  > Finally, in the Audit History tab, every single run is queryable, searchable, and backed by a complete SQLite transaction log with granular validation checks.
  > 
  > The entire solution is tested with 27 automated pytest tests, works completely offline in Demo Mode, and is ready for live deployment. Thank you!"*
