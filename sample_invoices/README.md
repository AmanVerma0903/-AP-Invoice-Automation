# Sample Invoices Directory & Expected Results Guide

This directory contains realistic, synthetic Accounts Payable invoice PDFs designed to test both standard execution and edge-case behaviors.

---

### Demo Test Matrix

| File Name | Vendor | PO Reference | Invoiced Total | Expected Decision | Key Business Reason & Mechanics |
|---|---|---|---|---|---|
| `01_happy_path_apex.pdf` | Apex Cloud Solutions LLC | `PO-2026-101` | **$5,000.00** | **Eligible for Approval** | Clean 1:1 match. Vendor approved, line items sum correctly ($4,500 + $500), amount matches PO exactly. PO balance reduced to $0.00. |
| `02_duplicate_original_glp.pdf` | Global Logistics Partners | `PO-2026-103` | **$8,400.00** | **Eligible for Approval** | Initial valid submission. Consumes PO-2026-103 balance down to $0.00. |
| `02_duplicate_resubmission_glp_renamed.pdf` | Global Logistics Partners | `PO-2026-103` | **$8,400.00** | **On Hold** (Edge Case 1) | Re-submission of Invoice # `INV-GLP-8801` with different file name. Detected via multi-factor vendor + invoice number check. Zero additional PO consumption. |
| `03a_split_po_milestone1_datacore.pdf` | Datacore Infrastructure Inc. | `PO-2026-102` | **$5,000.00** | **Eligible for Approval** (Edge Case 2 - Part 1) | Legitimate partial invoice against $12,500.00 PO. PO remaining balance safely decreases to $7,500.00. |
| `03b_split_po_milestone2_datacore.pdf` | Datacore Infrastructure Inc. | `PO-2026-102` | **$7,500.00** | **Eligible for Approval** (Edge Case 2 - Part 2) | Second legitimate milestone invoice. Fully consumes remaining $7,500.00. PO balance becomes $0.00. |
| `03c_split_po_overdraft_datacore.pdf` | Datacore Infrastructure Inc. | `PO-2026-102` | **$3,000.00** | **Manual Review** (Edge Case 2 - Part 3) | Vendor bills additional $3,000.00. Invoiced amount exceeds remaining PO balance ($0.00). Flagged for Change Order. |
| `04a_within_tolerance_apex.pdf` | Apex Cloud Solutions LLC | `PO-2026-101` | **$5,035.00** | **Eligible for Approval** (Edge Case 3 - Within Tolerance) | Discrepancy is +$35.00 (+0.7%). Configured policy allows min($50.00, 2% of $5,000 = $100) = $50.00. Approved with variance audit note. |
| `04b_exceeds_tolerance_apex.pdf` | Apex Cloud Solutions LLC | `PO-2026-101` | **$5,450.00** | **Manual Review** (Edge Case 3 - Material Discrepancy) | Discrepancy is +$450.00 (+9.0%), which exceeds the $50.00 maximum tolerance. Routed to AP reviewer for credit memo request. |
| `05_missing_invoice_number_apex.pdf` | Apex Cloud Solutions LLC | `PO-2026-101` | **$4,500.00** | **On Hold** (Edge Case 4 - Missing Data) | Mandatory `invoice_number` is missing. Legal liability cannot be established. Never hallucinated or guessed. |
| `06_blocked_vendor_blacklisted.pdf` | Blacklisted Supply Co. | `PO-2026-105` | **$3,200.00** | **On Hold** (Compliance Failure) | Vendor status is `BLOCKED` in master records. Payment frozen immediately. |
| `kent_invoice.pdf` | Kent RO Systems Limited | None (Order `405-3123402-7766752`) | **₹3,269.00** | **Manual Review** (Regression Test / E-commerce) | Real Amazon India GST invoice. Seller extracted from 'Sold By', date parsed as 2026-09-14, INR currency inferred, Net Amount ₹2,770.34 + IGST ₹498.66 = Total ₹3,269.00. Routes to Manual Review due to missing corporate PO and unlisted vendor. |

