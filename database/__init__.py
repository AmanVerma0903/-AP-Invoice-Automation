"""Database package for Zamp AP Invoice Automation."""

from database.db import (
    init_db,
    get_db_connection,
    get_all_vendors,
    find_vendor_by_name,
    find_vendor_by_id,
    get_all_purchase_orders,
    find_po_by_number,
    find_pos_for_vendor,
    check_duplicate_file_hash,
    check_duplicate_invoice_number,
    check_content_duplicate,
    save_invoice_result,
    get_dashboard_metrics,
    get_invoices_history,
    get_invoice_detail,
)

__all__ = [
    "init_db",
    "get_db_connection",
    "get_all_vendors",
    "find_vendor_by_name",
    "find_vendor_by_id",
    "get_all_purchase_orders",
    "find_po_by_number",
    "find_pos_for_vendor",
    "check_duplicate_file_hash",
    "check_duplicate_invoice_number",
    "check_content_duplicate",
    "save_invoice_result",
    "get_dashboard_metrics",
    "get_invoices_history",
    "get_invoice_detail",
]
