# ⚡ Zamp AP Invoice Automation — From PDF to Decision

[![Python](https://img.shields.io/badge/Python-3.10%20%7C%203.11%20%7C%203.12%20%7C%203.13-blue.svg)](https://www.python.org/)
[![Framework](https://img.shields.io/badge/Streamlit-1.35+-FF4B4B.svg)](https://streamlit.io/)
[![AI Engine](https://img.shields.io/badge/Google%20Gemini-Multimodal%20LLM-8E75C4.svg)](https://aistudio.google.com/)
[![Tests](https://img.shields.io/badge/Tests-38%2F38%20Passing%20(100%25)-success.svg)](tests/)
[![Architecture](https://img.shields.io/badge/Design-Deterministic%20Zero--Hallucination-emerald.svg)](#-architecture--8-stage-pipeline)

> **Production-grade Accounts Payable invoice processing, purchase order matching, deterministic financial validation, multi-document boundary detection, and explainable decision automation built for the Zamp AI Solutions Analyst hiring case study (Problem Statement 1).**

---

## 📌 Table of Contents
1. [Executive Summary & Problem Statement](#-executive-summary--problem-statement)
2. [Key Architecture & 8-Stage Pipeline](#-architecture--8-stage-pipeline)
3. [Strict AI vs. Deterministic Separation](#-strict-ai-vs-deterministic-separation)
4. [Edge Cases Handled & Realized Behavior](#-edge-cases-handled--realized-behavior)
5. [Real-World Multi-Document Partitioning](#-real-world-multi-document-partitioning)
6. [Human-in-the-Loop Reviewer Workspace](#-human-in-the-loop-reviewer-workspace)
7. [Comprehensive Test Suite (38/38 Passing)](#-comprehensive-test-suite-3838-passing)
8. [Quickstart & Local Installation](#-quickstart--local-installation)
9. [Deployment & Secrets Configuration](#-deployment--secrets-configuration)
10. [Repository Directory Structure](#-repository-directory-structure)
11. [5-Minute Demo Walkthrough Script](#-5-minute-demo-walkthrough-script)

---

## 🎯 Executive Summary & Problem Statement

In mid-sized enterprises, Accounts Payable (AP) departments receive hundreds of vendor invoices monthly via email as PDF attachments. The legacy manual workflow requires human operators to:
1. Open incoming invoice PDFs.
2. Manually key in invoice metadata (vendor name, invoice #, dates, currency, line items, subtotals, tax, and total amount).
3. Cross-reference procurement spreadsheets to locate the corresponding Purchase Order (PO).
4. Verify vendor approval status, check for duplicate submissions, confirm quantities, unit prices, arithmetic, and apply tolerance rules.
5. Determine invoice disposition: **`Eligible for Approval`**, **`Manual Review`**, or **`On Hold`**.
6. Document a defensible audit trail and business rationale for every decision.

Manual processing creates severe operational bottlenecks, high labor costs, slow payment cycles, and vulnerability to duplicate payments, unapproved vendor fraud, and PO overdrafts.

### The Solution:
This system automates the AP workflow end-to-end:
* Ingests arbitrary PDF invoices safely (MIME check, SHA-256 fingerprinting).
* Extracts structured headers and itemized line items via **Google Gemini Multimodal LLM** with an offline **Local Layout & Heuristics Fallback**.
* Reconciles invoices against real procurement records in an **ACID SQLite database**.
* Applies a **12-point deterministic validation engine** with strict tolerance policies ($\min(\$50.00, 2\%)$).
* Produces explainable 3-tier decisions with full evidence breakdown and interactive Human-in-the-Loop reviewer actions.

---

## 🏗️ Architecture & 8-Stage Pipeline

The system is structured around an 8-stage modular pipeline where every transformation, validation rule, and decision reason is visible:

```text
[Incoming PDF Invoice]
        │
        ▼
[Stage 1: Ingestion & Safety] ───► Validate MIME, file size (<10MB) & SHA-256 fingerprint
        │
        ▼
[Stage 2: Document Extraction] ──► Gemini AI / PyMuPDF OCR Fallback + Boundary Partitioning
        │
        ▼
[Stage 3: Normalization] ────────► Canonical legal entity names, ISO 8601 dates, currency
        │
        ▼
[Stage 4: PO Matcher] ───────────► PO lookup, remaining balance tracking & tolerance limits
        │
        ▼
[Stage 5: Deterministic Checks] ─► 12-point arithmetic, vendor approval & duplicate checks
        │
        ▼
[Stage 6: Decision Engine] ──────► Strict 3-level precedence hierarchy (Hold > Review > Pass)
        │
        ▼
[Stage 7: ACID Persistence] ─────► SQLite transaction, PO deduction & audit log commit
        │
        ▼
[Stage 8: UI & Human Workspace] ─► Streamlit Run View, AP Dashboard & Reviewer Action Tools
```

---

## 🛡️ Strict AI vs. Deterministic Separation

A fundamental design decision of this system is **zero hallucination in financial decision-making**:

* **What the AI does (Perception / Extraction):**
  Gemini is used strictly for reading messy, multi-column, and diverse invoice formats (extracting text, line-item tables, tax breakdowns, and vendor names into structured Pydantic models).
* **What the AI NEVER does (Financial Decisioning):**
  The AI is **never** asked *"Should this invoice be paid?"*
  All math verification (`subtotal + tax == total`), line-item sum reconciliation, duplicate detection, PO tolerance calculation, vendor approval verification, and final status assignment are executed by **100% deterministic, auditable Python rules**.

---

## 📌 Edge Cases Handled & Realized Behavior

As specified in the candidate requirements, the system implements and tests **4 realistic, non-trivial edge cases**:

| Edge Case | Scenario Tested | System Behavior | PO & Ledger Impact |
|:---|:---|:---|:---|
| **Edge Case 1: Duplicate Submission** | Re-uploading an identical PDF or a renamed copy (`02_duplicate_resubmission_glp_renamed.pdf`). | Multi-factor check detects identical SHA-256 hash OR matching `(vendor, invoice_number)`. Routes immediately to **`On Hold`**. | Zero additional balance consumed; prevents double payment. |
| **Edge Case 2: Split PO & Overdraft** | Vendor splits a $12,500 PO into multiple milestone invoices (`03a`: $5k, `03b`: $7.5k, `03c`: $3k). | Invoices `03a` and `03b` pass cleanly, reducing balance to $0.00 (`CLOSED`). Invoice `03c` is routed to **`Manual Review`** for PO balance overdraft. | Tracks cumulative balance atomically. Blocks unauthorized overages. |
| **Edge Case 3: Amount Discrepancy & Tolerance** | Invoice total differs from PO total (`04a`: $5,035 vs $5,000; `04b`: $5,450 vs $5,000). | Permitted variance: $\min(\$50.00, 2\% \times \text{PO})$. `04a` (+0.7%) is **`Eligible for Approval`** with variance notice; `04b` (+9.0%) is routed to **`Manual Review`**. | AP reviewer alerted with exact dollar delta and recommended actions. |
| **Edge Case 4: Missing or Unreliable Data** | Invoice is missing critical invoice number/date (`05_missing_...`) or issued by a blocked vendor (`06_blocked_...`). | Missing mandatory fields are flagged; never hallucinated or assumed zero. Blocked vendors trigger instant payment freeze (**`On Hold`**). | Halts processing until compliant vendor onboarding or re-issuance. |

---

## 📑 Real-World Multi-Document Partitioning

Real-world e-commerce invoices (such as Indian GST Flipkart/Amazon invoices) often combine multiple distinct seller invoices into a single multi-page PDF file:
* **Page 1:** Primary Seller (e.g., Shreyash Retail Pvt Ltd — ₹247.00)
* **Page 2:** Platform Logistics (e.g., Flipkart Internet Pvt Ltd — ₹10.00)

**How our system handles this:**
* **Boundary Detection:** Automatically partitions multi-document boundaries.
* **Independent Accounting:** Each document is parsed, validated, and accounted for as an isolated invoice entity with its own vendor tax ID, line items, and decision status.
* **Taxable Base vs. Tax-Inclusive Handling:** Correctly maps base net amount (`₹209.32`) to line items so that $\text{Subtotal} + \text{Tax} = \text{Total Amount}$ reconciles cleanly under GAAP/GST standards without double-counting tax.

---

## 👤 Human-in-the-Loop Reviewer Workspace

Rather than a passive dashboard, the application provides an active **AP Reviewer Authority Workspace**:

* **Clean Invoices (`APPROVAL_ELIGIBLE`):**
  * Processed via **Straight-Through Processing (STP)**.
  * No redundant approval clicks required; provides an optional `🚩 Route for Secondary Signoff` control.
* **Exception Invoices (`REVIEW_REQUIRED` & `ON_HOLD`):**
  * **`✍️ Override & Authorize Payment`:** Allows a senior reviewer to approve an exception with a mandatory audit justification (atomically deducts PO balance upon override).
  * **`📧 Vendor Discrepancy Notice`:** Automatically drafts a pre-filled, professional email to the vendor citing the exact discrepancy, missing PO, or variance.
  * **`🚫 Reject Invoice`:** Marks invoice rejected and automatically **refunds/restores any allocated PO balance**.
  * **`🚫 Confirm Fraud/Duplicate Hold`:** Escalates confirmed fraud to Compliance.

---

## 🧪 Comprehensive Test Suite (38/38 Passing)

The repository includes a complete automated test suite run via `pytest`:

```bash
pytest -v
```

```text
============================= test session starts =============================
platform win32 -- Python 3.13.1, pytest-9.1.1
collected 38 items

tests/test_decision_engine.py::test_clean_pass_is_approval_eligible PASSED       [ 2%]
tests/test_decision_engine.py::test_blocking_failure_precedence_on_hold PASSED   [ 5%]
tests/test_decision_engine.py::test_tolerance_variance_yields_review_required PASSED [ 7%]
tests/test_decision_engine.py::test_cumulative_balance_overdraft_yields_review_required PASSED [10%]
tests/test_decision_engine.py::test_human_reviewer_actions_lifecycle PASSED    [13%]
tests/test_edge_cases.py::test_edge_case_1_duplicate_invoice PASSED             [15%]
tests/test_edge_cases.py::test_edge_case_2_multiple_invoices_against_single_po PASSED [18%]
tests/test_edge_cases.py::test_edge_case_3_amount_discrepancy_and_tolerance PASSED [21%]
tests/test_edge_cases.py::test_edge_case_4_missing_invoice_data PASSED          [23%]
tests/test_extractor.py::test_validate_pdf_file PASSED                          [26%]
tests/test_extractor.py::test_extract_happy_path_pdf PASSED                     [28%]
tests/test_extractor.py::test_extract_missing_invoice_number PASSED             [31%]
tests/test_models.py::test_line_item_decimal_parsing PASSED                     [34%]
tests/test_models.py::test_extracted_invoice_defaults PASSED                    [36%]
tests/test_models.py::test_decision_status_display_labels PASSED                [39%]
tests/test_models.py::test_normalize_vendor_name PASSED                         [42%]
tests/test_models.py::test_normalize_date PASSED                                [44%]
tests/test_models.py::test_normalize_currency PASSED                            [47%]
tests/test_models.py::test_to_decimal PASSED                                    [50%]
tests/test_po_matcher.py::test_calculate_tolerance_limit PASSED                 [52%]
tests/test_po_matcher.py::test_exact_po_match PASSED                            [55%]
tests/test_po_matcher.py::test_within_tolerance_match PASSED                    [57%]
tests/test_po_matcher.py::test_exceeds_tolerance_match PASSED                   [60%]
tests/test_po_matcher.py::test_partial_invoice_match PASSED                     [63%]
tests/test_po_matcher.py::test_currency_mismatch PASSED                         [65%]
tests/test_regression_kent.py::test_kent_text_extraction PASSED                 [68%]
tests/test_regression_kent.py::test_kent_field_extraction PASSED                [71%]
tests/test_regression_kent.py::test_kent_missing_po_and_unregistered_vendor_behavior PASSED [73%]
tests/test_regression_kent.py::test_kent_arithmetic_consistency PASSED          [76%]
tests/test_regression_suite.py::test_regression_kent_ro_local_fallback PASSED   [78%]
tests/test_regression_suite.py::test_regression_adidas_and_flipkart_multidoc PASSED [81%]
tests/test_regression_suite.py::test_regression_sliced_invoices_local_fallback PASSED [84%]
tests/test_regression_suite.py::test_gemini_mode_mocked_success PASSED          [86%]
tests/test_regression_suite.py::test_gemini_mode_c_graceful_fallback PASSED    [89%]
tests/test_regression_suite.py::test_force_offline_mode_override PASSED         [92%]
tests/test_validator.py::test_missing_required_fields_fails PASSED              [94%]
tests/test_validator.py::test_arithmetic_consistency_check PASSED               [97%]
tests/test_validator.py::test_vendor_approval_statuses PASSED                   [100%]

======================= 38 passed in 28.56s =======================
```

---

## 🚀 Quickstart & Local Installation

### 1. Prerequisites
* Python 3.10, 3.11, 3.12, or 3.13
* Git

### 2. Clone and Setup Environment
```bash
# Clone the repository
git clone https://github.com/AmanVerma0903/-AP-Invoice-Automation.git
cd -AP-Invoice-Automation

# Create virtual environment
python -m venv .venv

# Activate virtual environment
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 3. Generate Scenario PDF Invoices
```bash
python sample_invoices/generate_samples.py
```

### 4. Configure Environment Variables
Create a `.env` file in the root directory (based on `.env.example`):
```env
GEMINI_API_KEY=your_gemini_api_key_here
GEMINI_MODEL=gemini-3.5-flash
MAX_TOLERANCE_USD=50.00
MAX_TOLERANCE_PERCENTAGE=0.02
DATABASE_PATH=zamp_ap.db
```
*(Note: If `GEMINI_API_KEY` is omitted, the application operates 100% offline using its deterministic local layout heuristic fallback).*

### 5. Launch the Application
```bash
streamlit run app.py
```
Open **[http://localhost:8501](http://localhost:8501)** in your browser.

---

## 🌐 Deployment & Secrets Configuration

### Deploying to Streamlit Community Cloud:
1. Push repository to GitHub (ensure `.env` is ignored by `.gitignore`).
2. Go to **[share.streamlit.io](https://share.streamlit.io/)** and click **New App**.
3. Select your repository (`AmanVerma0903/-AP-Invoice-Automation`), branch `main`, and main file `app.py`.
4. In **Advanced Settings > Secrets**, configure:
   ```toml
   GEMINI_API_KEY = "your-actual-gemini-api-key"
   GEMINI_MODEL = "gemini-3.5-flash"
   ```
5. Click **Deploy!**

---

## 📂 Repository Directory Structure

```text
-AP-Invoice-Automation/
├── app.py                         # Streamlit multi-tab enterprise interface
├── requirements.txt               # Production dependencies
├── README.md                      # Comprehensive system documentation
├── .gitignore                     # Git ignore rules (.env, *.db, cache)
├── .env.example                   # Environment configuration template
├── models/
│   ├── __init__.py
│   └── invoice.py                 # Pydantic models (ExtractedInvoice, POMatchResult, etc.)
├── services/
│   ├── __init__.py
│   ├── pdf_extractor.py           # PyMuPDF ingestion & layout text extraction
│   ├── ocr_service.py             # OCR fallback utilities
│   ├── llm_extractor.py           # Gemini multimodal & offline deterministic parser
│   ├── normalizer.py              # Canonical legal entity names, dates, currencies
│   ├── po_matcher.py              # Procurement matching, tolerance & cumulative balance
│   ├── validator.py               # 12-point deterministic validation engine
│   ├── decision_engine.py         # 3-Level precedence decision synthesizer
│   └── audit_service.py           # Pipeline orchestrator & persistence coordinator
├── database/
│   ├── __init__.py
│   ├── schema.sql                 # SQLite schema with foreign keys and indices
│   └── db.py                      # Database manager, transactions & seed logic
├── data/
│   ├── vendors.csv                # Master vendor records with approval statuses
│   └── purchase_orders.csv        # Realistic PO master data with remaining balances
├── sample_invoices/
│   ├── README.md                  # Testing guide for scenario test invoices
│   ├── generate_samples.py        # Programmatic scenario PDF generator
│   ├── 01_happy_path_apex.pdf
│   ├── 02_duplicate_original_glp.pdf
│   ├── 02_duplicate_resubmission_glp_renamed.pdf
│   ├── 03a_split_po_milestone1_datacore.pdf
│   ├── 03b_split_po_milestone2_datacore.pdf
│   ├── 03c_split_po_overdraft_datacore.pdf
│   ├── 04a_within_tolerance_apex.pdf
│   ├── 04b_exceeds_tolerance_apex.pdf
│   ├── 05_missing_invoice_number_apex.pdf
│   └── 06_blocked_vendor_blacklisted.pdf
├── tests/
│   ├── __init__.py
│   ├── test_models.py
│   ├── test_extractor.py
│   ├── test_po_matcher.py
│   ├── test_validator.py
│   ├── test_decision_engine.py
│   ├── test_edge_cases.py
│   ├── test_regression_kent.py
│   └── test_regression_suite.py
├── docs/
│   ├── assignment_requirements.md # Summary of candidate case study requirements
│   ├── architecture.md            # Technical design, data flow & database schema
│   ├── decision_rules.md          # Deterministic decision rules & precedence matrix
│   └── demo_walkthrough_script.md # 5-minute video & interview demo script
└── .streamlit/
    └── config.toml                # Custom dark enterprise UI theme
```

---

