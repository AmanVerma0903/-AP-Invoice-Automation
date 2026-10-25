"""Zamp AP Invoice Automation — Streamlit Web Application."""

import os
import io
import json
import time
from decimal import Decimal
from datetime import datetime
import streamlit as st
import pandas as pd
from dotenv import load_dotenv

# Load server-side environment variables from .env
load_dotenv(override=True)

# Core database and models
from database.db import (
    init_db,
    get_dashboard_metrics,
    get_invoices_history,
    get_invoice_detail,
    get_all_vendors,
    get_all_purchase_orders,
    find_po_by_number,
    apply_reviewer_decision,
    DEFAULT_DB_PATH,
)
from models.invoice import DecisionStatus, CheckStatus
from services.audit_service import process_invoice_pipeline

# Page Configuration
st.set_page_config(
    page_title="Zamp AP Invoice Automation",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom Enterprise CSS Styles
st.markdown("""
<style>
    /* Global Typography and Backgrounds */
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
    }
    
    .main-header {
        background: linear-gradient(135deg, #1e1b4b 0%, #312e81 50%, #4338ca 100%);
        padding: 24px 30px;
        border-radius: 12px;
        color: white;
        margin-bottom: 24px;
        box-shadow: 0 4px 20px -2px rgba(67, 56, 202, 0.25);
        border: 1px solid rgba(255, 255, 255, 0.1);
    }
    
    .main-title {
        font-size: 26px;
        font-weight: 700;
        margin: 0;
        color: #ffffff;
        letter-spacing: -0.02em;
    }
    
    .main-subtitle {
        font-size: 14px;
        color: #c7d2fe;
        margin-top: 6px;
        margin-bottom: 0;
    }
    
    /* Metrics Cards */
    .metric-card {
        background: #1e293b;
        border: 1px solid #334155;
        border-radius: 10px;
        padding: 18px 20px;
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.2);
        transition: transform 0.15s ease, border-color 0.15s ease;
    }
    .metric-card:hover {
        border-color: #6366f1;
        transform: translateY(-2px);
    }
    .metric-title {
        font-size: 12px;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        color: #94a3b8;
        margin-bottom: 8px;
    }
    .metric-val {
        font-size: 26px;
        font-weight: 700;
        color: #f8fafc;
        line-height: 1.1;
    }
    .metric-sub {
        font-size: 11px;
        color: #64748b;
        margin-top: 6px;
    }
    
    /* Decision Status Banners */
    .decision-banner-approved {
        background: linear-gradient(135deg, rgba(16, 185, 129, 0.15) 0%, rgba(5, 150, 105, 0.05) 100%);
        border: 1.5px solid #10b981;
        border-radius: 10px;
        padding: 20px 24px;
        margin-bottom: 20px;
    }
    .decision-banner-review {
        background: linear-gradient(135deg, rgba(245, 158, 11, 0.15) 0%, rgba(217, 119, 6, 0.05) 100%);
        border: 1.5px solid #f59e0b;
        border-radius: 10px;
        padding: 20px 24px;
        margin-bottom: 20px;
    }
    .decision-banner-hold {
        background: linear-gradient(135deg, rgba(239, 68, 68, 0.15) 0%, rgba(220, 38, 38, 0.05) 100%);
        border: 1.5px solid #ef4444;
        border-radius: 10px;
        padding: 20px 24px;
        margin-bottom: 20px;
    }
    
    /* Status Badges */
    .badge {
        display: inline-block;
        padding: 4px 10px;
        border-radius: 9999px;
        font-size: 11px;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.04em;
    }
    .badge-approved { background-color: #064e3b; color: #34d399; border: 1px solid #059669; }
    .badge-review { background-color: #78350f; color: #fbbf24; border: 1px solid #d97706; }
    .badge-hold { background-color: #7f1d1d; color: #f87171; border: 1px solid #dc2626; }
    .badge-neutral { background-color: #334155; color: #cbd5e1; }
    
    /* Stage Progress Steps */
    .stage-item {
        background: #1e293b;
        border-left: 4px solid #6366f1;
        padding: 10px 14px;
        border-radius: 0 8px 8px 0;
        margin-bottom: 8px;
        font-size: 13px;
    }
    
    /* Live Pipeline Stepper */
    .stepper-container {
        background: #0f172a;
        border: 1px solid #334155;
        border-radius: 10px;
        padding: 18px 22px;
        margin: 16px 0 20px 0;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.2);
    }
    .stepper-title {
        font-size: 14px;
        font-weight: 700;
        color: #f8fafc;
        margin-bottom: 12px;
        display: flex;
        justify-content: space-between;
        align-items: center;
        border-bottom: 1px solid #1e293b;
        padding-bottom: 8px;
    }
    .step-row {
        display: flex;
        align-items: flex-start;
        padding: 8px 12px;
        border-radius: 6px;
        margin-bottom: 6px;
        font-size: 13px;
        transition: all 0.2s ease;
    }
    .step-row-pending {
        background: rgba(30, 41, 59, 0.4);
        color: #64748b;
        border-left: 3px solid #334155;
    }
    .step-row-running {
        background: rgba(99, 102, 241, 0.14);
        color: #e0e7ff;
        border-left: 3px solid #6366f1;
        font-weight: 600;
        box-shadow: 0 0 10px rgba(99, 102, 241, 0.2);
    }
    .step-row-completed {
        background: rgba(16, 185, 129, 0.08);
        color: #f1f5f9;
        border-left: 3px solid #10b981;
    }
    .step-icon {
        margin-right: 12px;
        font-size: 14px;
        line-height: 1.2;
    }
    .step-summary {
        font-size: 11px;
        color: #94a3b8;
        margin-top: 2px;
        line-height: 1.4;
    }
</style>
""", unsafe_allow_html=True)


# Initialize DB on load
init_db(DEFAULT_DB_PATH)

# Sidebar Configuration
st.sidebar.markdown("### ⚙️ System Controls")

# Server-side Gemini Configuration Detection (Zero UI API Key entry)
gemini_key = os.getenv("GEMINI_API_KEY", "").strip()
gemini_model = os.getenv("GEMINI_MODEL", "gemini-3.5-flash").strip() or "gemini-3.5-flash"
has_gemini = bool(gemini_key and not gemini_key.startswith("your-") and len(gemini_key) > 10)

# Interactive Gemini AI Mode Toggle
gemini_toggle = st.sidebar.toggle(
    "⚡ Enable Gemini AI Mode",
    value=has_gemini,
    key="gemini_mode_toggle",
    help="When enabled, uses Google Gemini multimodal LLM for structured extraction. When disabled, uses 100% offline deterministic fallback."
)

if gemini_toggle:
    if has_gemini:
        st.sidebar.markdown(f"""
        <div style="background: rgba(16, 185, 129, 0.12); border: 1px solid rgba(16, 185, 129, 0.35); border-radius: 8px; padding: 12px; margin-bottom: 12px;">
            <div style="font-weight: 700; color: #10b981; font-size: 13px;">🟢 Gemini AI Mode Active</div>
            <div style="font-size: 12px; color: #cbd5e1; margin-top: 4px;">Model: <code>{gemini_model}</code></div>
            <div style="font-size: 11px; color: #94a3b8; margin-top: 4px;">Server-side API key detected. Extracting via multimodal LLM with OCR fallback.</div>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.sidebar.markdown("""
        <div style="background: rgba(245, 158, 11, 0.12); border: 1px solid rgba(245, 158, 11, 0.4); border-radius: 8px; padding: 12px; margin-bottom: 12px;">
            <div style="font-weight: 700; color: #fbbf24; font-size: 13px;">⚠️ Gemini AI Mode Not Available</div>
            <div style="font-size: 11px; color: #fef08a; margin-top: 4px;"><code>GEMINI_API_KEY</code> is not configured in <code>.env</code>.</div>
            <div style="font-size: 11px; color: #cbd5e1; margin-top: 4px;">Falling back automatically to local deterministic mode.</div>
        </div>
        """, unsafe_allow_html=True)
else:
    st.sidebar.markdown("""
    <div style="background: rgba(148, 163, 184, 0.08); border: 1px solid rgba(148, 163, 184, 0.25); border-radius: 8px; padding: 12px; margin-bottom: 12px;">
        <div style="font-weight: 700; color: #cbd5e1; font-size: 13px;">⚪ Local Fallback Mode Active</div>
        <div style="font-size: 12px; color: #94a3b8; margin-top: 4px;">Deterministic heuristic & layout parser. 100% offline, zero external requests.</div>
    </div>
    """, unsafe_allow_html=True)

st.sidebar.markdown("---")
st.sidebar.markdown("### 🗄️ Database Management")

if st.sidebar.button("🔄 Reset & Reseed Database", help="Restores pristine procurement data and resets PO balances."):
    init_db(DEFAULT_DB_PATH, force_reseed=True)
    st.sidebar.success("Database reseeded with fresh procurement master data!")
    time.sleep(0.5)
    st.rerun()

st.sidebar.markdown("---")
st.sidebar.markdown("### 📐 Tolerance Policy")
st.sidebar.markdown("""
- **Max Absolute Variance:** `$50.00`
- **Max Percentage Variance:** `2.0%`
- **Effective Tolerance:** `min($50.00, 2% * PO)`
- **Cumulative Invoicing:** Checked against remaining PO balance.
""")



# Header Banner
st.markdown("""
<div class="main-header">
    <div style="display: flex; justify-content: space-between; align-items: center;">
        <div>
            <h1 class="main-title">⚡ Zamp Accounts Payable Automation</h1>
            <p class="main-subtitle">Autonomous Invoice Ingestion, PO Matching, Deterministic Validation & Explainable Decision Engine</p>
        </div>
        <div style="text-align: right;">
            <span class="badge badge-approved">Enterprise AP Live</span>
            <div style="font-size: 11px; color: #a5b4fc; margin-top: 4px;">PS-1 · From PDF to Decision</div>
        </div>
    </div>
</div>
""", unsafe_allow_html=True)


# Main Tabs Navigation
tabs = st.tabs([
    "⚡ Process Invoice (Live Run)",
    "📊 AP Dashboard",
    "🗄️ Audit History & Search",
    "📋 Procurement Records",
])


# ==============================================================================
# TAB 1: PROCESS INVOICE (LIVE RUN)
# ==============================================================================
with tabs[0]:
    st.markdown("### 📥 Ingest & Process Vendor Invoice")

    sample_files_dir = os.path.join(os.path.dirname(__file__), "sample_invoices")
    available_samples = [
        "-- Select Pre-Packaged Demo Invoice --",
        "kent_invoice.pdf (Kent RO Systems: E-commerce INR Invoice ₹3,269)",
        "adidas_flipkart_multidoc.pdf (Adidas ₹3,199 + Flipkart ₹230 Multi-Document Split)",
        "sliced_invoices.pdf (DEMO - Sliced Invoices $93.50 Professional Services)",
        "01_happy_path_apex.pdf (Happy Path: Clean 1:1 Match $5,000)",
        "02_duplicate_original_glp.pdf (Original GLP Submission)",
        "02_duplicate_resubmission_glp_renamed.pdf (Edge Case 1: Renamed Duplicate File)",
        "03a_split_po_milestone1_datacore.pdf (Edge Case 2: Partial Invoice #1 $5,000)",
        "03b_split_po_milestone2_datacore.pdf (Edge Case 2: Partial Invoice #2 $7,500)",
        "03c_split_po_overdraft_datacore.pdf (Edge Case 2: PO Overdraft Invoice $3,000)",
        "04a_within_tolerance_apex.pdf (Edge Case 3: Within Tolerance $5,035)",
        "04b_exceeds_tolerance_apex.pdf (Edge Case 3: Exceeds Tolerance $5,450)",
        "05_missing_invoice_number_apex.pdf (Edge Case 4: Missing Invoice #)",
        "06_blocked_vendor_blacklisted.pdf (Blocked Vendor Check)",
    ]

    if "uploader_key" not in st.session_state:
        st.session_state["uploader_key"] = 0

    def on_sample_change():
        # When a demo invoice is selected in Option A, reset Option B uploader to clear any uploaded file
        if st.session_state.get("sample_selector") != available_samples[0]:
            st.session_state["uploader_key"] += 1

    def on_file_upload():
        # When a custom PDF is uploaded in Option B, reset Option A dropdown to default
        cur_uploader_key = f"custom_uploader_{st.session_state['uploader_key']}"
        if st.session_state.get(cur_uploader_key) is not None:
            st.session_state["sample_selector"] = available_samples[0]

    selected_sample = st.selectbox(
        "Option A: Select Pre-Packaged Scenario Invoice",
        options=available_samples,
        index=0,
        key="sample_selector",
        on_change=on_sample_change,
        help="Pre-configured realistic invoices covering all edge cases for live testing.",
    )

    uploaded_file = st.file_uploader(
        "Option B: Or Upload Custom Invoice PDF",
        type=["pdf"],
        key=f"custom_uploader_{st.session_state['uploader_key']}",
        on_change=on_file_upload,
        help="Upload any vendor invoice in PDF format (max 10MB).",
    )

    # Determine file to process
    active_file_bytes = None
    active_file_name = None

    if selected_sample != available_samples[0]:
        sample_basename = selected_sample.split(" ")[0]
        sample_path = os.path.join(sample_files_dir, sample_basename)
        if os.path.exists(sample_path):
            with open(sample_path, "rb") as f:
                active_file_bytes = f.read()
            active_file_name = sample_basename
            st.info(f"Loaded demo invoice: **{active_file_name}**")
    elif uploaded_file is not None:
        active_file_bytes = uploaded_file.read()
        active_file_name = uploaded_file.name
        st.success(f"Uploaded custom file: **{active_file_name}** ({len(active_file_bytes):,} bytes)")

    st.markdown("<br/>", unsafe_allow_html=True)
    process_btn = st.button("🚀 Process Invoice Through Pipeline", type="primary", disabled=(active_file_bytes is None))

    if process_btn and active_file_bytes:
        import time

        # Visual Live Pipeline Stepper placeholder
        stepper_placeholder = st.empty()

        use_offline = (not gemini_toggle) or (not has_gemini)
        extraction_desc = "Document boundary detection & Local Heuristic parsing" if use_offline else "Document boundary detection & Gemini AI parsing"

        stages_order = [
            ("STAGE_1_INGESTION", "Stage 1: Document Ingestion", "SHA-256 fingerprinting & MIME header validation"),
            ("STAGE_2_EXTRACTION", "Stage 2: Structural Extraction", extraction_desc),
            ("STAGE_3_NORMALIZATION", "Stage 3: Data Canonicalization", "Legal entity normalization, ISO dates & currency standards"),
            ("STAGE_4_PO_MATCHING", "Stage 4: PO Reconciliation", "Purchase order lookup, 2-way match & tolerance boundaries"),
            ("STAGE_5_VALIDATION", "Stage 5: Deterministic Validation", "12-point arithmetic, vendor status & duplicate checks"),
            ("STAGE_6_DECISION", "Stage 6: Precedence Decision", "Precedence rules evaluation (Approval / Review / Hold)"),
            ("STAGE_7_PERSISTENCE", "Stage 7: ACID Persistence", "PO balance deduction & timestamped audit log commit"),
        ]

        stage_status_map = {k: {"status": "PENDING", "details": d} for k, _, d in stages_order}

        def render_stepper(is_live=True):
            html = '<div class="stepper-container">'
            if is_live:
                header_text = '<span style="color: #6366f1;">⚡ Autonomous AP Pipeline Executing...</span>'
                badge_text = '<span style="font-size: 11px; background: rgba(99,102,241,0.2); color: #818cf8; padding: 2px 8px; border-radius: 4px;">RUNNING</span>'
            else:
                header_text = '<span style="color: #10b981;">✅ 7-Stage Autonomous AP Pipeline Completed</span>'
                badge_text = '<span style="font-size: 11px; background: rgba(16,185,129,0.2); color: #34d399; padding: 2px 8px; border-radius: 4px;">100% AUDITED</span>'

            html += f'<div class="stepper-title"><span>{header_text}</span><span>{badge_text}</span></div>'
            for key, label, default_desc in stages_order:
                info = stage_status_map[key]
                st_val = info["status"]
                det = info["details"]
                if st_val == "COMPLETED":
                    cls = "step-row step-row-completed"
                    icon = "✅"
                elif st_val == "RUNNING":
                    cls = "step-row step-row-running"
                    icon = "⏳"
                else:
                    cls = "step-row step-row-pending"
                    icon = "⚪"
                html += f'<div class="{cls}"><span class="step-icon">{icon}</span><div style="flex: 1;"><div style="font-size: 13px;">{label}</div><div class="step-summary">{det}</div></div></div>'
            html += '</div>'
            stepper_placeholder.markdown(html, unsafe_allow_html=True)

        # Initial render before running
        render_stepper(is_live=True)

        def step_tracker(step_name, status, details):
            if step_name in stage_status_map:
                stage_status_map[step_name]["status"] = status
                if details and "summary" in details:
                    stage_status_map[step_name]["details"] = details["summary"]
                render_stepper(is_live=True)
                # For quick local stages, introduce a tiny 0.15s micro-pause so the progression is human-readable
                if status == "COMPLETED" and step_name != "STAGE_2_EXTRACTION":
                    time.sleep(0.15)

        # Run Pipeline
        result = process_invoice_pipeline(
            file_name=active_file_name,
            file_bytes=active_file_bytes,
            db_path=DEFAULT_DB_PATH,
            step_callback=step_tracker,
            force_offline=use_offline,
        )

        # Mark all completed and render final completed stepper
        for k in stage_status_map:
            stage_status_map[k]["status"] = "COMPLETED"
        render_stepper(is_live=False)

        # -------------------------------------------------------------
        # RESULTS DISPLAY
        # -------------------------------------------------------------
        dec = result.decision
        ext = result.extracted_data
        po = result.po_match

        st.markdown("<br/>", unsafe_allow_html=True)

        # 1. Decision Status Banner
        if dec.status == DecisionStatus.APPROVAL_ELIGIBLE:
            banner_class = "decision-banner-approved"
            badge_html = '<span class="badge badge-approved" style="font-size: 14px; padding: 6px 14px;">ELIGIBLE FOR APPROVAL</span>'
        elif dec.status == DecisionStatus.REVIEW_REQUIRED:
            banner_class = "decision-banner-review"
            badge_html = '<span class="badge badge-review" style="font-size: 14px; padding: 6px 14px;">MANUAL REVIEW REQUIRED</span>'
        else:
            banner_class = "decision-banner-hold"
            badge_html = '<span class="badge badge-hold" style="font-size: 14px; padding: 6px 14px;">ON HOLD (BLOCKED)</span>'

        st.markdown(f"""
        <div class="{banner_class}">
            <div style="display: flex; justify-content: space-between; align-items: flex-start;">
                <div>
                    <div style="font-size: 12px; font-weight: 700; text-transform: uppercase; color: #94a3b8; letter-spacing: 0.05em;">FINAL DETERMINATION · {ext.extraction_method}</div>
                    <div style="font-size: 22px; font-weight: 700; color: #ffffff; margin-top: 4px;">{dec.primary_reason}</div>
                    <div style="font-size: 13px; color: #cbd5e1; margin-top: 8px;">Invoice ID: <code>{result.invoice_id}</code> · Processed at: {result.processing_timestamp.strftime('%Y-%m-%d %H:%M:%S')}</div>
                </div>
                <div style="text-align: right;">
                    {badge_html}
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)

        # 2. Key Actions and Highlights Columns
        col_reasons, col_actions = st.columns([1.2, 1.0])

        with col_reasons:
            st.markdown("#### 📋 Decision Rationale & Contributing Checks")
            for r in dec.all_reasons:
                if "[BLOCKING]" in r:
                    st.error(r)
                elif "[EXCEPTION]" in r:
                    st.warning(r)
                elif "[WARNING]" in r:
                    st.info(r)
                else:
                    st.success(r)

            if ext.extraction_warnings:
                for w in ext.extraction_warnings:
                    st.warning(f"⚠️ **Extraction Notice:** {w}")

        with col_actions:
            st.markdown("#### 🎯 Recommended AP Reviewer Next Actions")
            for act in dec.suggested_actions:
                st.markdown(f"- **Action:** {act}")

        st.markdown("<br/>", unsafe_allow_html=True)

        # -------------------------------------------------------------
        # HUMAN-IN-THE-LOOP AP REVIEWER ACTION CONTROLS
        # -------------------------------------------------------------
        action_session_key = f"decision_action_{result.invoice_id}"
        recorded_action = st.session_state.get(action_session_key)

        st.markdown("""
        <div style="background: linear-gradient(135deg, rgba(30, 41, 59, 0.85) 0%, rgba(15, 23, 42, 0.95) 100%);
                    border: 1.5px solid rgba(99, 102, 241, 0.45);
                    border-radius: 12px; padding: 18px 22px; margin-bottom: 16px;
                    box-shadow: 0 4px 20px rgba(0, 0, 0, 0.3);">
            <div style="display: flex; justify-content: space-between; align-items: center;">
                <div style="display: flex; align-items: center; gap: 12px;">
                    <div style="background: rgba(99, 102, 241, 0.2); border-radius: 8px; padding: 8px 10px; font-size: 20px;">👤</div>
                    <div>
                        <div style="font-size: 15px; font-weight: 700; color: #f8fafc; letter-spacing: 0.02em;">
                            Human-in-the-Loop AP Reviewer Authority
                        </div>
                        <div style="font-size: 12px; color: #94a3b8; margin-top: 2px;">
                            Review AI & deterministic rules output, execute authoritative signoff, or record compliant audit overrides.
                        </div>
                    </div>
                </div>
                <div style="text-align: right;">
                    <span class="badge badge-approved" style="font-size: 11px;">Operator: Senior AP Specialist</span>
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)

        if recorded_action:
            badge_cls = "badge-approved" if ("Authorized" in recorded_action["label"] or "Approved" in recorded_action["label"]) else "badge-hold"
            st.markdown(f"""
            <div style="background: rgba(16, 185, 129, 0.12); border: 1.5px solid #10b981; border-radius: 10px; padding: 16px 20px; margin-bottom: 20px;">
                <div style="display: flex; justify-content: space-between; align-items: center;">
                    <div style="font-weight: 700; color: #34d399; font-size: 15px;">
                        ✅ Reviewer Action Recorded: {recorded_action['label']}
                    </div>
                    <span class="badge {badge_cls}">Ledger Updated</span>
                </div>
                <div style="color: #e2e8f0; font-size: 13px; margin-top: 6px;">
                    {recorded_action['reason']}
                </div>
                <div style="color: #94a3b8; font-size: 11px; margin-top: 4px;">
                    Committed to SQLite audit ledger with immutable timestamp. Remaining PO balance adjusted accordingly.
                </div>
            </div>
            """, unsafe_allow_html=True)
        else:
            if dec.status == DecisionStatus.APPROVAL_ELIGIBLE:
                c_stp, c_signoff = st.columns([2.2, 1.1])
                with c_stp:
                    st.markdown("""
                    <div style="background: rgba(16, 185, 129, 0.08); border: 1px solid rgba(16, 185, 129, 0.3); border-radius: 8px; padding: 12px 16px;">
                        <div style="display: flex; justify-content: space-between; align-items: center;">
                            <span style="font-weight: 700; color: #34d399; font-size: 13px;">⚡ Zero-Touch Straight-Through Processing (STP) Active</span>
                            <span class="badge badge-approved" style="font-size: 10px;">Auto-Passed</span>
                        </div>
                        <div style="font-size: 12px; color: #cbd5e1; margin-top: 4px;">
                            All 12 validation rules satisfied. Invoice is automatically approved, PO balance committed, and queued for scheduled disbursement. Zero manual clicks required.
                        </div>
                    </div>
                    """, unsafe_allow_html=True)
                with c_signoff:
                    st.markdown("<div style='height: 4px;'></div>", unsafe_allow_html=True)
                    if st.button("🚩 Route for Secondary Signoff", use_container_width=True, key=f"btn_flag_{result.invoice_id}", help="Optional: Escalate to Finance Controller if you notice stale dates or high-value anomalies."):
                        res = apply_reviewer_decision(result.invoice_id, "FLAG_AUDIT", "Flagged by AP Reviewer for second-level manager signoff.", db_path=DEFAULT_DB_PATH)
                        st.session_state[action_session_key] = {
                            "label": "Secondary Audit Pending",
                            "reason": "Routed to Finance Controller for secondary executive review.",
                        }
                        st.info("Invoice flagged for secondary review.")
                        st.rerun()

            elif dec.status == DecisionStatus.REVIEW_REQUIRED:
                st.markdown("**Reviewer Resolution Actions:**")
                c_ovr, c_notice, c_rej = st.columns([1.2, 1.2, 1.0])

                with c_ovr:
                    with st.popover("✍️ Override & Authorize Payment", use_container_width=True):
                        st.markdown("##### Manual Exception Approval")
                        st.caption("Provide an audit reason to approve this invoice despite the rule flags.")
                        override_reason = st.text_input(
                            "Approval Justification Note:",
                            placeholder="e.g. Authorized by AP Lead: seasonal price increase pre-approved by procurement",
                            key=f"override_txt_{result.invoice_id}",
                        )
                        if st.button("Confirm Override Approval", type="primary", key=f"btn_confirm_ovr_{result.invoice_id}"):
                            if override_reason.strip():
                                res = apply_reviewer_decision(result.invoice_id, "MANUAL_OVERRIDE_APPROVE", override_reason.strip(), db_path=DEFAULT_DB_PATH)
                                st.session_state[action_session_key] = {
                                    "label": res["new_label"],
                                    "reason": res["primary_reason"],
                                }
                                st.success("Override recorded and PO balance updated!")
                                st.rerun()
                            else:
                                st.error("Please enter a justification note before confirming.")

                with c_notice:
                    with st.popover("📧 Vendor Discrepancy Notice", use_container_width=True):
                        st.markdown("##### Pre-Drafted Discrepancy Email")
                        st.caption("Auto-generated from PO matching facts and tolerance delta.")
                        var_amt = abs(po.amount_variance or Decimal('0.00'))
                        email_to = "billing@" + (ext.vendor_name or "vendor").lower().replace(" ", "").replace(",", "") + ".com"
                        email_body = (
                            f"To: {email_to}\n"
                            f"Subject: Action Required: Variance in Invoice #{ext.invoice_number or 'N/A'} (PO {po.po_number or 'N/A'})\n\n"
                            f"Dear {ext.vendor_name or 'Vendor'} Billing Team,\n\n"
                            f"During automated PO reconciliation for Invoice #{ext.invoice_number or 'N/A'}, a variance of "
                            f"${var_amt:,.2f} ({po.percentage_variance}%) was flagged against Purchase Order {po.po_number or 'N/A'}.\n\n"
                            f"Summary of Issue: {dec.primary_reason}\n\n"
                            f"Please provide an amended invoice or credit note.\n\n"
                            f"Accounts Payable Operations"
                        )
                        st.text_area("Copy Draft:", value=email_body, height=180)

                with c_rej:
                    if st.button("🚫 Reject Invoice", use_container_width=True, key=f"btn_rej_{result.invoice_id}"):
                        res = apply_reviewer_decision(result.invoice_id, "REJECT_INVOICE", "Invoice rejected by AP Reviewer due to unresolved discrepancy.", db_path=DEFAULT_DB_PATH)
                        st.session_state[action_session_key] = {
                            "label": res["new_label"],
                            "reason": res["primary_reason"],
                        }
                        st.warning("Invoice marked as Rejected.")
                        st.rerun()

            else:  # ON_HOLD
                c_hold1, c_hold2 = st.columns([1, 1])
                with c_hold1:
                    if st.button("🚫 Confirm Fraud/Duplicate Hold & Escalate", type="primary", use_container_width=True, key=f"btn_hold_esc_{result.invoice_id}"):
                        res = apply_reviewer_decision(result.invoice_id, "CONFIRM_HOLD", "Confirmed violation. Escalated to Security & Compliance.", db_path=DEFAULT_DB_PATH)
                        st.session_state[action_session_key] = {
                            "label": res["new_label"],
                            "reason": res["primary_reason"],
                        }
                        st.error("Hold confirmed and escalated to compliance.")
                        st.rerun()
                with c_hold2:
                    if st.button("🔄 Mark False Positive & Route to Exception Review", use_container_width=True, key=f"btn_hold_fp_{result.invoice_id}"):
                        res = apply_reviewer_decision(result.invoice_id, "FLAG_AUDIT", "Flagged by AP Reviewer as potential false positive for manual exception audit.", db_path=DEFAULT_DB_PATH)
                        st.session_state[action_session_key] = {
                            "label": "Manual Exception Review Pending",
                            "reason": "False positive flagged: routed to senior AP reviewer queue.",
                        }
                        st.info("Routed to exception review.")
                        st.rerun()

        # Multi-document Boundary Section (if separate documents detected in same PDF)
        if result.sub_results:
            st.markdown("---")
            st.markdown("#### 📑 Multi-Document Boundary Partitioning")
            st.info(f"**Document Boundaries Detected:** This PDF contains **{len(result.sub_results) + 1} distinct documents**. "
                    "Each document was parsed, validated, and accounted for independently to prevent financial distortion.")
            for sub_res in result.sub_results:
                s_ext = sub_res.extracted_data
                s_curr = "₹" if s_ext.currency == "INR" else "$"
                st.markdown(f"""
                <div style="background: rgba(30, 41, 59, 0.7); border: 1px solid rgba(148, 163, 184, 0.2); border-radius: 8px; padding: 14px; margin-bottom: 10px;">
                    <div style="display: flex; justify-content: space-between;">
                        <span style="font-weight: 700; color: #38bdf8;">📄 {s_ext.document_type} (Pages: {', '.join(map(str, s_ext.page_references))})</span>
                        <span style="color: #f59e0b; font-weight: 600;">Status: {sub_res.decision.display_label}</span>
                    </div>
                    <div style="margin-top: 6px; font-size: 13px; color: #cbd5e1;">
                        <strong>Vendor:</strong> {s_ext.vendor_name or 'N/A'} · 
                        <strong>Document #:</strong> <code>{s_ext.invoice_number or 'N/A'}</code> · 
                        <strong>Total:</strong> <span style="font-weight: 700; color: #ffffff;">{s_curr}{s_ext.total_amount or 0:,.2f} ({s_ext.currency})</span>
                    </div>
                    <div style="font-size: 12px; color: #94a3b8; margin-top: 4px;">{sub_res.decision.primary_reason}</div>
                </div>
                """, unsafe_allow_html=True)

        st.markdown("---")

        # 3. Side-by-side Inspection: Extracted Fields vs PO Matching
        col_ext, col_po = st.columns(2)

        with col_ext:
            st.markdown("#### 📄 Extracted Invoice Fields")
            curr_sym = "₹" if ext.currency == "INR" else ("€" if ext.currency == "EUR" else ("£" if ext.currency == "GBP" else "$"))
            ext_data = {
                "Field": [
                    "Extraction Engine",
                    "Document Type",
                    "Vendor Name",
                    "GSTIN / Tax ID",
                    "PAN",
                    "Invoice Number",
                    "Order Number",
                    "Invoice Date",
                    "Payment Due Date",
                    "Currency",
                    "Subtotal (Taxable Value)",
                    "Tax Amount",
                    "Total Amount"
                ],
                "Extracted Value": [
                    ext.extraction_method,
                    ext.document_type or "Invoice",
                    ext.vendor_name or "❌ MISSING",
                    ext.gstin or ext.vendor_tax_id or "N/A",
                    ext.pan or "N/A",
                    ext.invoice_number or "❌ MISSING",
                    ext.order_number or "N/A",
                    str(ext.invoice_date) if ext.invoice_date else "❌ MISSING",
                    str(ext.due_date) if ext.due_date else "N/A",
                    ext.currency or "USD",
                    f"{curr_sym}{ext.subtotal:,.2f}" if ext.subtotal is not None else "N/A",
                    f"{curr_sym}{ext.tax_amount:,.2f}" if ext.tax_amount is not None else "N/A",
                    f"{curr_sym}{ext.total_amount:,.2f}" if ext.total_amount is not None else "❌ MISSING",
                ]
            }
            st.table(pd.DataFrame(ext_data))

            if ext.line_items:
                st.markdown("**Itemized Line Items:**")
                items_rows = []
                for it in ext.line_items:
                    items_rows.append({
                        "Description": it.description,
                        "Qty": str(it.quantity) if it.quantity is not None else "1",
                        "Unit Price (Net Taxable)": f"{curr_sym}{it.unit_price:,.2f}" if it.unit_price is not None else "-",
                        "Taxable Amount": f"{curr_sym}{it.amount:,.2f}",
                    })
                st.dataframe(pd.DataFrame(items_rows), use_container_width=True, hide_index=True)

        with col_po:
            st.markdown("#### 📦 Purchase Order Reconciliation")
            if po.is_matched:
                po_rows = [
                    {"Metric": "Matched PO Number", "Value": po.po_number or "None"},
                    {"Metric": "Procurement Vendor", "Value": po.matched_vendor_name or "N/A"},
                    {"Metric": "Original PO Commitment", "Value": f"${po.po_total:,.2f}" if po.po_total else "N/A"},
                    {"Metric": "Remaining Unbilled Balance", "Value": f"${po.po_remaining_balance:,.2f}" if po.po_remaining_balance else "N/A"},
                    {"Metric": "Amount Variance (|Inv - PO|)", "Value": f"${abs(po.amount_variance or 0):,.2f} ({po.percentage_variance}%)"},
                    {"Metric": "Allowable Tolerance Limit", "Value": f"${po.tolerance_threshold_used:,.2f}" if po.tolerance_threshold_used else "$50.00"},
                    {"Metric": "Within Tolerance?", "Value": "✅ YES" if po.within_tolerance else "❌ NO (Exceeds Tolerance)"},
                    {"Metric": "Partial Invoice?", "Value": "Yes (Milestone/Partial)" if po.is_partial_invoice else "No (Full Billed)"},
                    {"Metric": "Exceeds Remaining Balance?", "Value": "🚨 YES (Overdraft Exception)" if po.exceeds_remaining_balance else "No (Sufficient Balance)"},
                ]
                st.table(pd.DataFrame(po_rows))
            else:
                st.warning(f"No Purchase Order matched. {po.explanation}")

        # 4. Granular Validation Checklist Table
        st.markdown("#### ✅ Complete Validation Checklist")
        val_rows = []
        for chk in result.validation_checks:
            val_rows.append({
                "Rule Name": chk.check_name,
                "Status": "✅ PASS" if chk.status == CheckStatus.PASS else ("⚠️ WARN" if chk.status == CheckStatus.WARN else "❌ FAIL"),
                "Blocking?": "Yes (Hold)" if chk.is_blocking else "No",
                "Expected Value": chk.expected or "-",
                "Actual Value": chk.actual or "-",
                "Detail Explanation": chk.message,
            })
        st.dataframe(pd.DataFrame(val_rows), use_container_width=True, hide_index=True)


        # 5. Raw Text and Audit Log Expander
        with st.expander("🔍 View Raw PDF Extracted Text & Audit Event Log"):
            st.markdown("**Chronological Pipeline Events:**")
            st.json(result.audit_events)
            st.markdown("**Raw PDF Text Layer:**")
            st.code(ext.raw_text or "No text", language="text")


# ==============================================================================
# TAB 2: AP EXECUTIVE DASHBOARD
# ==============================================================================
with tabs[1]:
    st.markdown("### 📊 Accounts Payable Processing Metrics")
    metrics = get_dashboard_metrics(DEFAULT_DB_PATH)

    m1, m2, m3, m4, m5, m6 = st.columns(6)

    m1.markdown(f"""
    <div class="metric-card">
        <div class="metric-title">Total Invoices</div>
        <div class="metric-val">{metrics['total_invoices']}</div>
        <div class="metric-sub">Processed in system</div>
    </div>
    """, unsafe_allow_html=True)

    m2.markdown(f"""
    <div class="metric-card" style="border-top: 3px solid #10b981;">
        <div class="metric-title">Eligible Approval</div>
        <div class="metric-val" style="color: #34d399;">{metrics['approved_count']}</div>
        <div class="metric-sub">Ready for payment</div>
    </div>
    """, unsafe_allow_html=True)

    m3.markdown(f"""
    <div class="metric-card" style="border-top: 3px solid #f59e0b;">
        <div class="metric-title">Manual Review</div>
        <div class="metric-val" style="color: #fbbf24;">{metrics['review_count']}</div>
        <div class="metric-sub">Variances / Splits</div>
    </div>
    """, unsafe_allow_html=True)

    m4.markdown(f"""
    <div class="metric-card" style="border-top: 3px solid #ef4444;">
        <div class="metric-title">On Hold</div>
        <div class="metric-val" style="color: #f87171;">{metrics['hold_count']}</div>
        <div class="metric-sub">Duplicates & Blocked</div>
    </div>
    """, unsafe_allow_html=True)

    m5.markdown(f"""
    <div class="metric-card">
        <div class="metric-title">Total Invoiced</div>
        <div class="metric-val">${metrics['total_value']:,.0f}</div>
        <div class="metric-sub">Cumulative processed</div>
    </div>
    """, unsafe_allow_html=True)

    m6.markdown(f"""
    <div class="metric-card">
        <div class="metric-title">Exceptions</div>
        <div class="metric-val" style="color: #cbd5e1;">{metrics['exception_count']}</div>
        <div class="metric-sub">Fails & warnings</div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("<br/>", unsafe_allow_html=True)

    # Status Distribution Visual
    if metrics["total_invoices"] > 0:
        col_chart, col_summary = st.columns([1.2, 1.0])

        with col_chart:
            st.markdown("#### Invoice Disposition Breakdown")
            df_chart = pd.DataFrame({
                "Disposition": ["Eligible for Approval", "Manual Review", "On Hold"],
                "Count": [metrics["approved_count"], metrics["review_count"], metrics["hold_count"]],
            })
            st.bar_chart(df_chart.set_index("Disposition"), color=["#6366f1"])

        with col_summary:
            st.markdown("#### AP Operational Health")
            auto_rate = (metrics["approved_count"] / metrics["total_invoices"]) * 100 if metrics["total_invoices"] > 0 else 0
            st.markdown(f"""
            - **Straight-Through Processing (STP) Rate:** `{auto_rate:.1f}%`
            - **Manual Intervention Queue:** `{metrics['review_count']} invoices`
            - **Blocked Invoices on Hold:** `{metrics['hold_count']} invoices`
            - **Audit Trail Coverage:** `100% of runs recorded`
            """)
            st.info("💡 **Operational Insight:** Invoices on hold are automatically prevented from double-consuming purchase order allocations.")
    else:
        st.info("No invoices processed in database yet. Navigate to 'Process Invoice' to run invoices through the pipeline.")


# ==============================================================================
# TAB 3: AUDIT HISTORY & SEARCH
# ==============================================================================
with tabs[2]:
    st.markdown("### 🗄️ Historical Invoices & Audit Ledger")

    col_search, col_filter = st.columns([2, 1])
    search_q = col_search.text_input("🔍 Search Invoices", placeholder="Search by vendor, invoice #, file name, or PO #...")
    status_select = col_filter.selectbox("Filter Status", ["ALL", "APPROVAL_ELIGIBLE", "REVIEW_REQUIRED", "ON_HOLD"])

    history_records = get_invoices_history(
        search_term=search_q if search_q else None,
        status_filter=status_select,
        limit=100,
        db_path=DEFAULT_DB_PATH,
    )

    if history_records:
        history_table_data = []
        for r in history_records:
            history_table_data.append({
                "Invoice ID": r["id"],
                "File Name": r["file_name"],
                "Vendor": r["vendor_name"] or "N/A",
                "Invoice #": r["invoice_number"] or "N/A",
                "Date": str(r["invoice_date"]) if r["invoice_date"] else "N/A",
                "Amount": f"${r['total_amount']:,.2f}" if r["total_amount"] is not None else "N/A",
                "PO Reference": r["po_number"] or "N/A",
                "Status": r["display_label"],
                "Primary Reason": r["primary_reason"][:60] + "..." if len(r["primary_reason"] or "") > 60 else r["primary_reason"],
                "Processed At": r["created_at"][:19] if r["created_at"] else "",
            })

        df_hist = pd.DataFrame(history_table_data)
        st.dataframe(df_hist, use_container_width=True, hide_index=True)

        # Drilldown details selector
        st.markdown("---")
        st.markdown("#### 🔎 Drill Down into Invoice Audit Record")
        selected_id = st.selectbox(
            "Select Invoice ID to inspect full audit record:",
            options=[r["id"] for r in history_records],
        )

        if selected_id:
            inv_detail = get_invoice_detail(selected_id, db_path=DEFAULT_DB_PATH)
            if inv_detail:
                d_col1, d_col2 = st.columns(2)
                with d_col1:
                    st.markdown(f"**Invoice ID:** `{inv_detail['id']}`")
                    st.markdown(f"**Status:** `{inv_detail['display_label']}`")
                    st.markdown(f"**File Name:** `{inv_detail['file_name']}`")
                    st.markdown(f"**File SHA-256:** `{inv_detail['file_hash']}`")
                    st.markdown(f"**Primary Decision Reason:** {inv_detail['primary_reason']}")

                with d_col2:
                    if inv_detail.get("po_consumption"):
                        cons = inv_detail["po_consumption"]
                        st.markdown("**PO Consumption Ledger:**")
                        st.markdown(f"- PO Number: `{cons['po_number']}`")
                        st.markdown(f"- Invoiced Amount: `${cons['invoiced_amount']:,.2f}`")
                        st.markdown(f"- Previous Balance: `${cons['previous_balance']:,.2f}`")
                        st.markdown(f"- New Balance: `${cons['new_balance']:,.2f}`")
                        st.markdown(f"- Consumed At: `{cons['consumed_at']}`")
                    else:
                        st.markdown("**PO Consumption:** None (Invoice was not approved or did not consume PO balance).")

                # Validation checks accordion
                if inv_detail.get("validations"):
                    st.markdown("**Saved Validation Checks:**")
                    st.dataframe(pd.DataFrame(inv_detail["validations"]), use_container_width=True, hide_index=True)

                # Chronological audit logs
                if inv_detail.get("audit_logs"):
                    st.markdown("**Chronological Event Ledger:**")
                    st.dataframe(pd.DataFrame(inv_detail["audit_logs"]), use_container_width=True, hide_index=True)

    else:
        st.info("No matching historical invoices found.")


# ==============================================================================
# TAB 4: PROCUREMENT RECORDS (VENDORS & POS)
# ==============================================================================
with tabs[3]:
    st.markdown("### 📋 Procurement Master Dataset")

    col_v, col_p = st.columns([1, 1.2])

    with col_v:
        st.markdown("#### Master Vendor Records")
        vendors = get_all_vendors(DEFAULT_DB_PATH)
        df_vendors = pd.DataFrame(vendors)
        if not df_vendors.empty:
            st.dataframe(
                df_vendors[["vendor_id", "name", "approval_status", "tax_id", "currency"]],
                use_container_width=True,
                hide_index=True,
            )

    with col_p:
        st.markdown("#### Purchase Orders & Real-Time Remaining Balances")
        pos = get_all_purchase_orders(DEFAULT_DB_PATH)
        df_pos = pd.DataFrame(pos)
        if not df_pos.empty:
            df_pos["total_amount_fmt"] = df_pos["total_amount"].apply(lambda x: f"${x:,.2f}")
            df_pos["remaining_balance_fmt"] = df_pos["remaining_balance"].apply(lambda x: f"${x:,.2f}")
            st.dataframe(
                df_pos[["po_number", "vendor_name", "total_amount_fmt", "remaining_balance_fmt", "status", "issue_date"]],
                use_container_width=True,
                hide_index=True,
            )

    st.info("💡 **Real-time Balance Deductions:** When an invoice is determined as **Eligible for Approval**, the `remaining_balance` of the matching PO is atomically updated in the SQLite database.")

