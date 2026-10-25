-- Schema for Zamp AP Invoice Automation

CREATE TABLE IF NOT EXISTS vendors (
    vendor_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    normalized_name TEXT NOT NULL,
    tax_id TEXT,
    approval_status TEXT NOT NULL CHECK(approval_status IN ('APPROVED', 'PENDING_REVIEW', 'BLOCKED')),
    currency TEXT NOT NULL DEFAULT 'USD',
    contact_email TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS purchase_orders (
    po_number TEXT PRIMARY KEY,
    vendor_id TEXT NOT NULL,
    total_amount NUMERIC NOT NULL,
    remaining_balance NUMERIC NOT NULL,
    currency TEXT NOT NULL DEFAULT 'USD',
    status TEXT NOT NULL CHECK(status IN ('OPEN', 'PARTIALLY_FULFILLED', 'CLOSED', 'CANCELLED')),
    issue_date DATE NOT NULL,
    line_items_json TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(vendor_id) REFERENCES vendors(vendor_id)
);

CREATE TABLE IF NOT EXISTS invoices (
    id TEXT PRIMARY KEY,
    file_name TEXT NOT NULL,
    file_hash TEXT NOT NULL,
    vendor_id TEXT,
    vendor_name TEXT,
    invoice_number TEXT,
    invoice_date DATE,
    currency TEXT,
    subtotal NUMERIC,
    tax_amount NUMERIC,
    total_amount NUMERIC,
    po_number TEXT,
    status TEXT NOT NULL CHECK(status IN ('APPROVAL_ELIGIBLE', 'REVIEW_REQUIRED', 'ON_HOLD', 'FAILED')),
    display_label TEXT NOT NULL,
    primary_reason TEXT,
    all_reasons_json TEXT,
    extracted_data_json TEXT,
    normalized_data_json TEXT,
    po_match_json TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS po_consumptions (
    id TEXT PRIMARY KEY,
    po_number TEXT NOT NULL,
    invoice_id TEXT NOT NULL UNIQUE,
    invoiced_amount NUMERIC NOT NULL,
    previous_balance NUMERIC NOT NULL,
    new_balance NUMERIC NOT NULL,
    consumed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(po_number) REFERENCES purchase_orders(po_number),
    FOREIGN KEY(invoice_id) REFERENCES invoices(id)
);

CREATE TABLE IF NOT EXISTS validation_results (
    id TEXT PRIMARY KEY,
    invoice_id TEXT NOT NULL,
    check_name TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('PASS', 'WARN', 'FAIL')),
    is_blocking BOOLEAN DEFAULT 0,
    expected_value TEXT,
    actual_value TEXT,
    message TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(invoice_id) REFERENCES invoices(id)
);

CREATE TABLE IF NOT EXISTS audit_logs (
    id TEXT PRIMARY KEY,
    invoice_id TEXT,
    event_type TEXT NOT NULL,
    description TEXT NOT NULL,
    metadata_json TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Indices for performance and duplicate detection
CREATE INDEX IF NOT EXISTS idx_invoices_file_hash ON invoices(file_hash);
CREATE INDEX IF NOT EXISTS idx_invoices_vendor_num ON invoices(vendor_name, invoice_number);
CREATE INDEX IF NOT EXISTS idx_invoices_status ON invoices(status);
CREATE INDEX IF NOT EXISTS idx_po_vendor ON purchase_orders(vendor_id);
