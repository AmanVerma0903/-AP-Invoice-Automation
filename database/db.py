"""Database manager and repository for Zamp AP Invoice Automation."""

import os
import csv
import json
import sqlite3
import uuid
from decimal import Decimal
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime

DEFAULT_DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "zamp_ap.db")


def get_db_connection(db_path: str = DEFAULT_DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def init_db(db_path: str = DEFAULT_DB_PATH, force_reseed: bool = False):
    """Initialize tables and load seed data if empty or forced."""
    base_dir = os.path.dirname(os.path.dirname(__file__))
    schema_path = os.path.join(base_dir, "database", "schema.sql")

    with open(schema_path, "r", encoding="utf-8") as f:
        schema_sql = f.read()

    conn = get_db_connection(db_path)
    try:
        with conn:
            conn.executescript(schema_sql)

        # Check if vendors exist
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM vendors")
        vendor_count = cursor.fetchone()[0]

        if vendor_count == 0 or force_reseed:
            seed_data(conn, base_dir, force_reseed=force_reseed)
    finally:
        conn.close()


def seed_data(conn: sqlite3.Connection, base_dir: str, force_reseed: bool = False):
    """Seed vendors and purchase orders from CSV files."""
    vendors_csv = os.path.join(base_dir, "data", "vendors.csv")
    po_csv = os.path.join(base_dir, "data", "purchase_orders.csv")

    with conn:
        if force_reseed:
            conn.execute("DELETE FROM po_consumptions")
            conn.execute("DELETE FROM validation_results")
            conn.execute("DELETE FROM audit_logs")
            conn.execute("DELETE FROM invoices")
            conn.execute("DELETE FROM purchase_orders")
            conn.execute("DELETE FROM vendors")

        if os.path.exists(vendors_csv):
            with open(vendors_csv, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    conn.execute(
                        """
                        INSERT OR REPLACE INTO vendors
                        (vendor_id, name, normalized_name, tax_id, approval_status, currency, contact_email)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            row["vendor_id"],
                            row["name"],
                            row["normalized_name"],
                            row.get("tax_id"),
                            row["approval_status"],
                            row.get("currency", "USD"),
                            row.get("contact_email"),
                        ),
                    )

        if os.path.exists(po_csv):
            with open(po_csv, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    conn.execute(
                        """
                        INSERT OR REPLACE INTO purchase_orders
                        (po_number, vendor_id, total_amount, remaining_balance, currency, status, issue_date, line_items_json)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            row["po_number"],
                            row["vendor_id"],
                            float(row["total_amount"]),
                            float(row["remaining_balance"]),
                            row.get("currency", "USD"),
                            row.get("status", "OPEN"),
                            row["issue_date"],
                            row.get("line_items_json", "[]"),
                        ),
                    )


# Vendor Queries
def get_all_vendors(db_path: str = DEFAULT_DB_PATH) -> List[Dict[str, Any]]:
    conn = get_db_connection(db_path)
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM vendors ORDER BY name ASC")
        return [dict(row) for row in cur.fetchall()]
    finally:
        conn.close()


def find_vendor_by_name(name: str, db_path: str = DEFAULT_DB_PATH) -> Optional[Dict[str, Any]]:
    if not name:
        return None
    conn = get_db_connection(db_path)
    try:
        cur = conn.cursor()
        # Direct exact or case-insensitive match
        cur.execute("SELECT * FROM vendors WHERE LOWER(name) = LOWER(?)", (name.strip(),))
        row = cur.fetchone()
        if row:
            return dict(row)

        # Check normalized match
        from services.normalizer import normalize_vendor_name
        norm = normalize_vendor_name(name)
        cur.execute("SELECT * FROM vendors WHERE normalized_name = ?", (norm,))
        row = cur.fetchone()
        if row:
            return dict(row)
        return None
    finally:
        conn.close()


def find_vendor_by_id(vendor_id: str, db_path: str = DEFAULT_DB_PATH) -> Optional[Dict[str, Any]]:
    conn = get_db_connection(db_path)
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM vendors WHERE vendor_id = ?", (vendor_id,))
        row = cur.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


# Purchase Order Queries
def get_all_purchase_orders(db_path: str = DEFAULT_DB_PATH) -> List[Dict[str, Any]]:
    conn = get_db_connection(db_path)
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT po.*, v.name as vendor_name, v.approval_status as vendor_status
            FROM purchase_orders po
            LEFT JOIN vendors v ON po.vendor_id = v.vendor_id
            ORDER BY po.issue_date DESC
        """)
        return [dict(row) for row in cur.fetchall()]
    finally:
        conn.close()


def find_po_by_number(po_number: str, db_path: str = DEFAULT_DB_PATH) -> Optional[Dict[str, Any]]:
    if not po_number:
        return None
    conn = get_db_connection(db_path)
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT po.*, v.name as vendor_name, v.approval_status as vendor_status
            FROM purchase_orders po
            LEFT JOIN vendors v ON po.vendor_id = v.vendor_id
            WHERE LOWER(po.po_number) = LOWER(?)
        """, (po_number.strip(),))
        row = cur.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def find_pos_for_vendor(vendor_id: str, db_path: str = DEFAULT_DB_PATH) -> List[Dict[str, Any]]:
    conn = get_db_connection(db_path)
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT * FROM purchase_orders
            WHERE vendor_id = ?
            ORDER BY issue_date DESC
        """, (vendor_id,))
        return [dict(row) for row in cur.fetchall()]
    finally:
        conn.close()


# Duplicate Checks
def check_duplicate_file_hash(file_hash: str, db_path: str = DEFAULT_DB_PATH) -> Optional[Dict[str, Any]]:
    conn = get_db_connection(db_path)
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT id, file_name, vendor_name, invoice_number, total_amount, status, created_at
            FROM invoices
            WHERE file_hash = ?
            ORDER BY created_at ASC LIMIT 1
        """, (file_hash,))
        row = cur.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def check_duplicate_invoice_number(vendor_name: str, invoice_number: str, db_path: str = DEFAULT_DB_PATH) -> Optional[Dict[str, Any]]:
    if not vendor_name or not invoice_number:
        return None
    conn = get_db_connection(db_path)
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT id, file_name, vendor_name, invoice_number, total_amount, status, created_at
            FROM invoices
            WHERE LOWER(vendor_name) = LOWER(?) AND LOWER(invoice_number) = LOWER(?)
            ORDER BY created_at ASC LIMIT 1
        """, (vendor_name.strip(), invoice_number.strip()))
        row = cur.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def check_content_duplicate(vendor_name: str, total_amount: float, invoice_date: str, db_path: str = DEFAULT_DB_PATH) -> Optional[Dict[str, Any]]:
    if not vendor_name or not total_amount or not invoice_date:
        return None
    conn = get_db_connection(db_path)
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT id, file_name, vendor_name, invoice_number, total_amount, invoice_date, status, created_at
            FROM invoices
            WHERE LOWER(vendor_name) = LOWER(?) 
              AND ABS(total_amount - ?) < 0.01 
              AND invoice_date = ?
            ORDER BY created_at ASC LIMIT 1
        """, (vendor_name.strip(), float(total_amount), str(invoice_date)))
        row = cur.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


# Persistence and Transactional Management
def save_invoice_result(result_dict: Dict[str, Any], db_path: str = DEFAULT_DB_PATH) -> str:
    """Save complete invoice processing result with ACID transaction and PO balance deduction."""
    conn = get_db_connection(db_path)
    invoice_id = result_dict.get("invoice_id") or str(uuid.uuid4())
    now_str = datetime.now().isoformat()

    with conn:
        cur = conn.cursor()

        # Check if this invoice ID already exists to guarantee idempotency
        cur.execute("SELECT id, status FROM invoices WHERE id = ?", (invoice_id,))
        existing = cur.fetchone()
        if existing:
            # Already saved
            return invoice_id

        # Insert Invoice record
        ext = result_dict.get("extracted_data", {})
        norm = result_dict.get("normalized_data", {})
        dec = result_dict.get("decision", {})
        po_match = result_dict.get("po_match", {})

        cur.execute(
            """
            INSERT INTO invoices (
                id, file_name, file_hash, vendor_id, vendor_name,
                invoice_number, invoice_date, currency, subtotal, tax_amount, total_amount,
                po_number, status, display_label, primary_reason, all_reasons_json,
                extracted_data_json, normalized_data_json, po_match_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                invoice_id,
                result_dict.get("file_name", "unknown.pdf"),
                result_dict.get("file_hash", ""),
                norm.get("vendor_id"),
                ext.get("vendor_name"),
                ext.get("invoice_number"),
                str(ext.get("invoice_date")) if ext.get("invoice_date") else None,
                ext.get("currency", "USD"),
                float(ext.get("subtotal")) if ext.get("subtotal") is not None else None,
                float(ext.get("tax_amount")) if ext.get("tax_amount") is not None else None,
                float(ext.get("total_amount")) if ext.get("total_amount") is not None else None,
                po_match.get("po_number"),
                dec.get("status", "REVIEW_REQUIRED"),
                dec.get("display_label", "Manual Review"),
                dec.get("primary_reason", ""),
                json.dumps(dec.get("all_reasons", [])),
                json.dumps(ext, default=str),
                json.dumps(norm, default=str),
                json.dumps(po_match, default=str),
                now_str,
                now_str,
            ),
        )

        # Insert Validation Results
        validations = result_dict.get("validation_checks", [])
        for v in validations:
            v_id = str(uuid.uuid4())
            cur.execute(
                """
                INSERT INTO validation_results (
                    id, invoice_id, check_name, status, is_blocking, expected_value, actual_value, message, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    v_id,
                    invoice_id,
                    v.get("check_name"),
                    v.get("status"),
                    1 if v.get("is_blocking") else 0,
                    str(v.get("expected")) if v.get("expected") is not None else None,
                    str(v.get("actual")) if v.get("actual") is not None else None,
                    v.get("message", ""),
                    now_str,
                ),
            )

        # PO Balance Consumption: ONLY IF APPROVAL_ELIGIBLE and matched PO exists and has not been consumed yet
        matched_po = po_match.get("po_number")
        is_approval_eligible = dec.get("status") == "APPROVAL_ELIGIBLE"
        invoice_total = ext.get("total_amount")

        if is_approval_eligible and matched_po and invoice_total is not None:
            # Check if this invoice already consumed from PO
            cur.execute("SELECT id FROM po_consumptions WHERE invoice_id = ?", (invoice_id,))
            already_consumed = cur.fetchone()

            if not already_consumed:
                # Fetch current remaining balance
                cur.execute("SELECT total_amount, remaining_balance FROM purchase_orders WHERE po_number = ?", (matched_po,))
                po_row = cur.fetchone()
                if po_row:
                    prev_bal = Decimal(str(po_row["remaining_balance"]))
                    inv_amt = Decimal(str(invoice_total))
                    new_bal = max(Decimal("0.00"), prev_bal - inv_amt)

                    # Update PO remaining balance
                    new_status = "CLOSED" if new_bal == Decimal("0.00") else "PARTIALLY_FULFILLED"
                    cur.execute(
                        "UPDATE purchase_orders SET remaining_balance = ?, status = ? WHERE po_number = ?",
                        (float(new_bal), new_status, matched_po),
                    )

                    # Record consumption
                    consumption_id = str(uuid.uuid4())
                    cur.execute(
                        """
                        INSERT INTO po_consumptions (id, po_number, invoice_id, invoiced_amount, previous_balance, new_balance, consumed_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (consumption_id, matched_po, invoice_id, float(inv_amt), float(prev_bal), float(new_bal), now_str),
                    )

        # Record Audit Logs
        audit_events = result_dict.get("audit_events", [])
        for event in audit_events:
            cur.execute(
                """
                INSERT INTO audit_logs (id, invoice_id, event_type, description, metadata_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    str(uuid.uuid4()),
                    invoice_id,
                    event.get("event_type", "INFO"),
                    event.get("description", ""),
                    json.dumps(event.get("metadata", {}), default=str),
                    event.get("timestamp", now_str),
                ),
            )

    conn.close()
    return invoice_id


# Dashboard Metrics Queries
def get_dashboard_metrics(db_path: str = DEFAULT_DB_PATH) -> Dict[str, Any]:
    conn = get_db_connection(db_path)
    try:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM invoices")
        total_invoices = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM invoices WHERE status = 'APPROVAL_ELIGIBLE'")
        approved_count = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM invoices WHERE status = 'REVIEW_REQUIRED'")
        review_count = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM invoices WHERE status = 'ON_HOLD'")
        hold_count = cur.fetchone()[0]

        cur.execute("SELECT COALESCE(SUM(total_amount), 0.0) FROM invoices")
        total_value = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM validation_results WHERE status IN ('FAIL', 'WARN')")
        exception_count = cur.fetchone()[0]

        return {
            "total_invoices": total_invoices,
            "approved_count": approved_count,
            "review_count": review_count,
            "hold_count": hold_count,
            "total_value": float(total_value),
            "exception_count": exception_count,
        }
    finally:
        conn.close()


# Historical Invoices Query with Search and Filter
def get_invoices_history(
    search_term: Optional[str] = None,
    status_filter: Optional[str] = None,
    limit: int = 50,
    db_path: str = DEFAULT_DB_PATH,
) -> List[Dict[str, Any]]:
    conn = get_db_connection(db_path)
    try:
        cur = conn.cursor()
        query = "SELECT * FROM invoices WHERE 1=1"
        params = []

        if status_filter and status_filter != "ALL":
            query += " AND status = ?"
            params.append(status_filter)

        if search_term:
            term = f"%{search_term.strip().lower()}%"
            query += """ AND (
                LOWER(file_name) LIKE ? OR 
                LOWER(COALESCE(vendor_name, '')) LIKE ? OR 
                LOWER(COALESCE(invoice_number, '')) LIKE ? OR 
                LOWER(COALESCE(po_number, '')) LIKE ?
            )"""
            params.extend([term, term, term, term])

        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        cur.execute(query, params)
        rows = cur.fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def get_invoice_detail(invoice_id: str, db_path: str = DEFAULT_DB_PATH) -> Optional[Dict[str, Any]]:
    conn = get_db_connection(db_path)
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM invoices WHERE id = ?", (invoice_id,))
        inv_row = cur.fetchone()
        if not inv_row:
            return None
        res = dict(inv_row)

        # Parse JSON fields
        for field in ["all_reasons_json", "extracted_data_json", "normalized_data_json", "po_match_json"]:
            if res.get(field):
                try:
                    res[field] = json.loads(res[field])
                except Exception:
                    pass

        # Fetch validations
        cur.execute("SELECT * FROM validation_results WHERE invoice_id = ? ORDER BY created_at ASC", (invoice_id,))
        res["validations"] = [dict(r) for r in cur.fetchall()]

        # Fetch consumption
        cur.execute("SELECT * FROM po_consumptions WHERE invoice_id = ?", (invoice_id,))
        cons = cur.fetchone()
        res["po_consumption"] = dict(cons) if cons else None

        # Fetch audit logs
        cur.execute("SELECT * FROM audit_logs WHERE invoice_id = ? ORDER BY created_at ASC", (invoice_id,))
        logs = []
        for r in cur.fetchall():
            d = dict(r)
            if d.get("metadata_json"):
                try:
                    d["metadata"] = json.loads(d["metadata_json"])
                except Exception:
                    pass
            logs.append(d)
        res["audit_logs"] = logs

        return res
    finally:
        conn.close()


def apply_reviewer_decision(
    invoice_id: str,
    action: str,
    reviewer_note: str = "",
    reviewer_name: str = "Senior AP Specialist",
    db_path: str = DEFAULT_DB_PATH,
) -> Dict[str, Any]:
    """Record an authoritative human-in-the-loop reviewer action and update invoice state & PO balance."""
    conn = get_db_connection(db_path)
    now_str = datetime.now().isoformat()
    try:
        with conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM invoices WHERE id = ?", (invoice_id,))
            inv_row = cur.fetchone()
            if not inv_row:
                return {"success": False, "message": f"Invoice {invoice_id} not found."}

            current_status = inv_row["status"]
            po_number = inv_row["po_number"]
            total_amount = Decimal(str(inv_row["total_amount"])) if inv_row["total_amount"] is not None else None

            new_status = current_status
            new_label = inv_row["display_label"]
            primary_reason = inv_row["primary_reason"]
            event_type = f"HUMAN_{action}"
            log_desc = f"Action '{action}' performed by {reviewer_name}."
            if reviewer_note:
                log_desc += f" Note: {reviewer_note}"

            po_deducted = False

            if action == "AUTHORIZE_PAYMENT":
                new_status = "APPROVAL_ELIGIBLE"
                new_label = "Payment Authorized"
                primary_reason = f"Payment authorized by {reviewer_name}. {reviewer_note}".strip()
                # Ensure PO consumption is recorded if not already
                if po_number and total_amount:
                    cur.execute("SELECT id FROM po_consumptions WHERE invoice_id = ?", (invoice_id,))
                    if not cur.fetchone():
                        cur.execute("SELECT remaining_balance FROM purchase_orders WHERE po_number = ?", (po_number,))
                        po_r = cur.fetchone()
                        if po_r:
                            prev_bal = Decimal(str(po_r["remaining_balance"]))
                            new_bal = max(Decimal("0.00"), prev_bal - total_amount)
                            cur.execute(
                                "UPDATE purchase_orders SET remaining_balance = ?, status = ? WHERE po_number = ?",
                                (float(new_bal), "CLOSED" if new_bal == 0 else "PARTIALLY_FULFILLED", po_number),
                            )
                            cur.execute(
                                """
                                INSERT INTO po_consumptions (id, po_number, invoice_id, invoiced_amount, previous_balance, new_balance, consumed_at)
                                VALUES (?, ?, ?, ?, ?, ?, ?)
                                """,
                                (str(uuid.uuid4()), po_number, invoice_id, float(total_amount), float(prev_bal), float(new_bal), now_str),
                            )
                            po_deducted = True

            elif action == "MANUAL_OVERRIDE_APPROVE":
                new_status = "APPROVAL_ELIGIBLE"
                new_label = "Approved (Reviewer Override)"
                primary_reason = f"[REVIEWER OVERRIDE] {reviewer_note or 'Manually approved by AP Reviewer.'}"
                # Deduct PO balance if not already deducted
                if po_number and total_amount:
                    cur.execute("SELECT id FROM po_consumptions WHERE invoice_id = ?", (invoice_id,))
                    if not cur.fetchone():
                        cur.execute("SELECT remaining_balance FROM purchase_orders WHERE po_number = ?", (po_number,))
                        po_r = cur.fetchone()
                        if po_r:
                            prev_bal = Decimal(str(po_r["remaining_balance"]))
                            new_bal = max(Decimal("0.00"), prev_bal - total_amount)
                            cur.execute(
                                "UPDATE purchase_orders SET remaining_balance = ?, status = ? WHERE po_number = ?",
                                (float(new_bal), "CLOSED" if new_bal == 0 else "PARTIALLY_FULFILLED", po_number),
                            )
                            cur.execute(
                                """
                                INSERT INTO po_consumptions (id, po_number, invoice_id, invoiced_amount, previous_balance, new_balance, consumed_at)
                                VALUES (?, ?, ?, ?, ?, ?, ?)
                                """,
                                (str(uuid.uuid4()), po_number, invoice_id, float(total_amount), float(prev_bal), float(new_bal), now_str),
                            )
                            po_deducted = True

            elif action == "REJECT_INVOICE":
                new_status = "ON_HOLD"
                new_label = "Rejected by Reviewer"
                primary_reason = f"[REVIEWER REJECTED] {reviewer_note or 'Rejected during manual AP audit.'}"
                # If this invoice had previously consumed from PO, refund/restore the allocated balance!
                cur.execute("SELECT po_number, invoiced_amount FROM po_consumptions WHERE invoice_id = ?", (invoice_id,))
                cons_row = cur.fetchone()
                if cons_row:
                    cons_po = cons_row["po_number"]
                    cons_amt = Decimal(str(cons_row["invoiced_amount"]))
                    cur.execute("SELECT total_amount, remaining_balance FROM purchase_orders WHERE po_number = ?", (cons_po,))
                    po_r = cur.fetchone()
                    if po_r:
                        tot_po = Decimal(str(po_r["total_amount"]))
                        cur_bal = Decimal(str(po_r["remaining_balance"]))
                        restored_bal = min(tot_po, cur_bal + cons_amt)
                        cur.execute(
                            "UPDATE purchase_orders SET remaining_balance = ?, status = ? WHERE po_number = ?",
                            (float(restored_bal), "OPEN" if restored_bal == tot_po else "PARTIALLY_FULFILLED", cons_po),
                        )
                        cur.execute("DELETE FROM po_consumptions WHERE invoice_id = ?", (invoice_id,))

            elif action == "CONFIRM_HOLD":
                new_status = "ON_HOLD"
                new_label = "Hold Confirmed & Escalated"
                primary_reason = f"[HOLD CONFIRMED] Escalated to compliance: {reviewer_note or 'Confirmed violation.'}"

            # Update invoice record
            cur.execute(
                """
                UPDATE invoices
                SET status = ?, display_label = ?, primary_reason = ?, updated_at = ?
                WHERE id = ?
                """,
                (new_status, new_label, primary_reason, now_str, invoice_id),
            )

            # Insert audit log entry
            cur.execute(
                """
                INSERT INTO audit_logs (id, invoice_id, event_type, description, metadata_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    str(uuid.uuid4()),
                    invoice_id,
                    event_type,
                    log_desc,
                    json.dumps({"action": action, "reviewer": reviewer_name, "note": reviewer_note, "po_deducted": po_deducted}),
                    now_str,
                ),
            )

            return {
                "success": True,
                "new_status": new_status,
                "new_label": new_label,
                "primary_reason": primary_reason,
                "po_deducted": po_deducted,
            }
    finally:
        conn.close()

