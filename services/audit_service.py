"""Orchestration pipeline and audit persistence for AP invoice processing."""

import uuid
from datetime import datetime
from typing import Dict, Any, Optional, Callable

from models.invoice import (
    CompleteProcessingResult,
    DecisionStatus,
    ExtractedInvoice,
    DecisionResult,
    POMatchResult,
)
from database.db import (
    save_invoice_result,
    check_duplicate_file_hash,
    check_duplicate_invoice_number,
    init_db,
    DEFAULT_DB_PATH,
)
from services.pdf_extractor import validate_pdf_file, extract_text_from_pdf, compute_file_hash
from services.llm_extractor import extract_invoice_data
from services.normalizer import normalize_invoice_payload
from services.po_matcher import match_purchase_order
from services.validator import run_all_validations
from services.decision_engine import evaluate_decision


def process_invoice_pipeline(
    file_name: str,
    file_bytes: bytes,
    api_key: Optional[str] = None,
    db_path: str = DEFAULT_DB_PATH,
    step_callback: Optional[Callable[[str, str, Dict[str, Any]], None]] = None,
    force_offline: bool = False,
) -> CompleteProcessingResult:
    """Execute end-to-end 8-stage invoice processing pipeline with real-time progress callbacks.
    
    Stages:
    1. Ingestion & Security
    2. Document Extraction (PyMuPDF / OCR / LLM)
    3. Data Normalization
    4. Purchase Order Matching
    5. Deterministic Validation
    6. Decision Synthesis
    7. Transactional Persistence & Audit
    8. Return Complete Result
    """
    # Ensure database is initialized
    init_db(db_path=db_path)
    
    invoice_id = f"INV-{uuid.uuid4().hex[:8].upper()}"
    start_time = datetime.now()
    audit_events = []

    def notify(step_name: str, status: str, details: Dict[str, Any]):
        timestamp = datetime.now().isoformat()
        audit_events.append({
            "event_type": step_name,
            "description": details.get("summary", ""),
            "metadata": details,
            "timestamp": timestamp,
        })
        if step_callback:
            step_callback(step_name, status, details)

    # -------------------------------------------------------------
    # STAGE 1: INGESTION & SECURITY VALIDATION
    # -------------------------------------------------------------
    notify("STAGE_1_INGESTION", "RUNNING", {"summary": f"Ingesting '{file_name}' ({len(file_bytes)} bytes)..."})
    is_valid_pdf, err_msg = validate_pdf_file(file_name, file_bytes)
    file_hash = compute_file_hash(file_bytes)
    
    if not is_valid_pdf:
        notify("STAGE_1_INGESTION", "FAILED", {"summary": f"File validation failed: {err_msg}"})
        # Generate failed decision
        dec = DecisionResult(
            status=DecisionStatus.FAILED,
            display_label="Processing Failed",
            primary_reason=err_msg or "Invalid PDF upload.",
            all_reasons=[err_msg or "Invalid PDF upload."],
            suggested_actions=["Upload a valid uncorrupted PDF file under 10MB."],
        )
        empty_ext = ExtractedInvoice()
        return CompleteProcessingResult(
            invoice_id=invoice_id,
            file_name=file_name,
            file_hash=file_hash,
            processing_timestamp=start_time,
            extracted_data=empty_ext,
            normalized_data={},
            validation_checks=[],
            po_match=POMatchResult(),
            decision=dec,
            audit_events=audit_events,
        )

    notify("STAGE_1_INGESTION", "COMPLETED", {
        "summary": "File validated successfully. SHA-256 fingerprint generated.",
        "file_hash": file_hash[:16] + "...",
        "file_size": len(file_bytes),
    })

    # -------------------------------------------------------------
    # STAGE 2: DOCUMENT EXTRACTION (PyMuPDF / OCR / LLM)
    # -------------------------------------------------------------
    notify("STAGE_2_EXTRACTION", "RUNNING", {"summary": "Extracting text layers and detecting document boundaries..."})
    raw_doc = extract_text_from_pdf(file_bytes)
    raw_text = raw_doc["raw_text"]
    boundaries = raw_doc.get("document_boundaries", [])
    pages = raw_doc.get("pages", [])

    # If multiple distinct documents are detected in this PDF, isolate primary document
    if boundaries and len(boundaries) > 1 and pages:
        primary_pages = boundaries[0]
        primary_text = "\n\n--- PAGE BREAK ---\n\n".join(pages[p] for p in primary_pages)
        extracted: ExtractedInvoice = extract_invoice_data(primary_text, force_offline=force_offline)
        extracted.page_references = [p + 1 for p in primary_pages]
    else:
        extracted = extract_invoice_data(raw_text, force_offline=force_offline)
        extracted.page_references = list(range(1, raw_doc.get("page_count", 1) + 1))
    
    # Merge any low-level PDF warnings
    if raw_doc["warnings"]:
        extracted.extraction_warnings.extend(raw_doc["warnings"])

    sub_results: List[CompleteProcessingResult] = []

    # Process secondary documents (e.g. separate Bill of Supply) if present
    if boundaries and len(boundaries) > 1 and pages:
        for doc_idx, sub_pages in enumerate(boundaries[1:], start=2):
            sub_text = "\n\n--- PAGE BREAK ---\n\n".join(pages[p] for p in sub_pages)
            sub_ext = extract_invoice_data(sub_text, force_offline=force_offline)
            sub_ext.page_references = [p + 1 for p in sub_pages]
            sub_norm = normalize_invoice_payload(sub_ext.model_dump())
            sub_po = match_purchase_order(sub_ext, sub_norm, db_path=db_path)
            sub_vals = run_all_validations(sub_ext, sub_norm, sub_po, file_hash, db_path=db_path)
            sub_dec = evaluate_decision(sub_ext, sub_vals, sub_po)
            sub_res = CompleteProcessingResult(
                invoice_id=f"{invoice_id}-D{doc_idx}",
                file_name=file_name,
                file_hash=file_hash,
                processing_timestamp=start_time,
                extracted_data=sub_ext,
                normalized_data=sub_norm,
                validation_checks=sub_vals,
                po_match=sub_po,
                decision=sub_dec,
                audit_events=[],
            )
            sub_results.append(sub_res)
            extracted.sub_invoices.append(sub_ext)

    curr_symbol = "₹" if extracted.currency == "INR" else ("€" if extracted.currency == "EUR" else "$")
    sub_summary_extra = f" + {len(sub_results)} separate sub-document(s)" if sub_results else ""
    notify("STAGE_2_EXTRACTION", "COMPLETED", {
        "summary": f"Extracted {len(extracted.line_items)} line items. Vendor: '{extracted.vendor_name or 'Unknown'}'. Total: {curr_symbol}{extracted.total_amount or 0:,.2f} ({extracted.currency}){sub_summary_extra}.",
        "is_scanned": raw_doc["is_scanned"],
        "confidence": extracted.extraction_confidence,
        "method": extracted.extraction_method,
    })

    # -------------------------------------------------------------
    # STAGE 3: DATA NORMALIZATION
    # -------------------------------------------------------------
    notify("STAGE_3_NORMALIZATION", "RUNNING", {"summary": "Normalizing legal entity names, ISO dates, and currencies..."})
    normalized = normalize_invoice_payload(extracted.model_dump())
    notify("STAGE_3_NORMALIZATION", "COMPLETED", {
        "summary": f"Canonical vendor: '{normalized['normalized_vendor_name']}', Date: {normalized['normalized_invoice_date']}, Currency: {normalized['normalized_currency']}",
    })

    # -------------------------------------------------------------
    # STAGE 4: PURCHASE ORDER MATCHING
    # -------------------------------------------------------------
    notify("STAGE_4_PO_MATCHING", "RUNNING", {"summary": f"Matching against procurement records for PO '{extracted.po_reference or 'N/A'}'..."})
    po_match = match_purchase_order(extracted, normalized, db_path=db_path)
    notify("STAGE_4_PO_MATCHING", "COMPLETED", {
        "summary": po_match.explanation,
        "is_matched": po_match.is_matched,
        "po_number": po_match.po_number,
        "remaining_balance": float(po_match.po_remaining_balance) if po_match.po_remaining_balance else None,
    })

    # -------------------------------------------------------------
    # STAGE 5: DETERMINISTIC VALIDATION
    # -------------------------------------------------------------
    notify("STAGE_5_VALIDATION", "RUNNING", {"summary": "Running financial, vendor status, duplicate, and arithmetic checks..."})
    validation_checks = run_all_validations(extracted, normalized, po_match, file_hash, db_path=db_path)
    fail_count = sum(1 for c in validation_checks if c.status.value == "FAIL")
    warn_count = sum(1 for c in validation_checks if c.status.value == "WARN")
    notify("STAGE_5_VALIDATION", "COMPLETED", {
        "summary": f"Executed {len(validation_checks)} validation rules: {len(validation_checks) - fail_count - warn_count} passed, {fail_count} failed, {warn_count} warnings.",
    })

    # -------------------------------------------------------------
    # STAGE 6: DECISION SYNTHESIS
    # -------------------------------------------------------------
    notify("STAGE_6_DECISION", "RUNNING", {"summary": "Synthesizing business outcome and action recommendations..."})
    decision = evaluate_decision(extracted, validation_checks, po_match)
    notify("STAGE_6_DECISION", "COMPLETED", {
        "summary": f"Outcome: {decision.display_label} — {decision.primary_reason}",
        "status": decision.status.value,
    })

    # -------------------------------------------------------------
    # STAGE 7: PERSISTENCE & AUDIT TRAIL
    # -------------------------------------------------------------
    notify("STAGE_7_PERSISTENCE", "RUNNING", {"summary": "Committing transaction to database and updating PO balance..."})
    complete_dict = {
        "invoice_id": invoice_id,
        "file_name": file_name,
        "file_hash": file_hash,
        "processing_timestamp": start_time.isoformat(),
        "extracted_data": extracted.model_dump(),
        "normalized_data": normalized,
        "validation_checks": [c.model_dump() for c in validation_checks],
        "po_match": po_match.model_dump(),
        "decision": decision.model_dump(),
        "audit_events": audit_events,
    }
    
    saved_id = save_invoice_result(complete_dict, db_path=db_path)
    notify("STAGE_7_PERSISTENCE", "COMPLETED", {"summary": f"Saved invoice record '{saved_id}' to audit ledger."})

    # -------------------------------------------------------------
    # STAGE 8: COMPLETE RESULT
    # -------------------------------------------------------------
    result = CompleteProcessingResult(
        invoice_id=invoice_id,
        file_name=file_name,
        file_hash=file_hash,
        processing_timestamp=start_time,
        extracted_data=extracted,
        normalized_data=normalized,
        validation_checks=validation_checks,
        po_match=po_match,
        decision=decision,
        audit_events=audit_events,
        sub_results=sub_results,
    )
    return result

    return result
