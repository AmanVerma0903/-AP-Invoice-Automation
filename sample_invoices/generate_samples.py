"""Script to generate realistic synthetic invoice PDFs for testing and live demo."""

import os
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    HRFlowable,
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle


def create_invoice_pdf(
    file_path: str,
    vendor_name: str,
    vendor_address: str,
    vendor_tax_id: str,
    invoice_number: str,
    invoice_date: str,
    due_date: str,
    po_reference: str,
    bill_to: str,
    line_items: list,
    subtotal: float,
    tax_amount: float,
    total_amount: float,
    currency: str = "USD",
    notes: str = "Thank you for your business. Payment terms: Net 30 days.",
):
    """Generate a clean, professional corporate invoice PDF."""
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    doc = SimpleDocTemplate(
        file_path,
        pagesize=letter,
        rightMargin=40,
        leftMargin=40,
        topMargin=40,
        bottomMargin=40,
    )
    styles = getSampleStyleSheet()

    # Custom styles
    title_style = ParagraphStyle(
        "InvoiceTitle",
        parent=styles["Heading1"],
        fontName="Helvetica-Bold",
        fontSize=24,
        leading=28,
        textColor=colors.HexColor("#1e293b"),
    )
    vendor_header_style = ParagraphStyle(
        "VendorHeader",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=14,
        leading=18,
        textColor=colors.HexColor("#0f172a"),
    )
    body_style = ParagraphStyle(
        "BodyDark",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9,
        leading=13,
        textColor=colors.HexColor("#334155"),
    )
    bold_body_style = ParagraphStyle(
        "BoldBodyDark",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=9,
        leading=13,
        textColor=colors.HexColor("#0f172a"),
    )
    meta_label = ParagraphStyle(
        "MetaLabel",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=9,
        leading=12,
        textColor=colors.HexColor("#64748b"),
    )

    curr_sym = "€" if currency == "EUR" else ("£" if currency == "GBP" else "$")
    story = []

    # Header section: Vendor info on left, INVOICE title on right
    vendor_info = [
        Paragraph(vendor_name, vendor_header_style),
        Paragraph(vendor_address, body_style),
        Paragraph(f"Tax ID / EIN: {vendor_tax_id}" if vendor_tax_id else "", body_style),
    ]

    invoice_meta = [
        Paragraph("INVOICE", title_style),
        Paragraph(f"<b>Invoice #:</b> {invoice_number or 'MISSING'}", bold_body_style),
        Paragraph(f"<b>Invoice Date:</b> {invoice_date or 'MISSING'}", body_style),
        Paragraph(f"<b>Payment Due:</b> {due_date or 'Net 30'}", body_style),
        Paragraph(f"<b>PO Reference:</b> {po_reference or 'None'}", bold_body_style),
    ]

    header_table = Table(
        [[vendor_info, invoice_meta]],
        colWidths=[300, 230],
    )
    header_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ALIGN", (1, 0), (1, 0), "RIGHT"),
    ]))
    story.append(header_table)
    story.append(Spacer(1, 15))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#cbd5e1"), spaceBefore=5, spaceAfter=15))

    # Bill To Box
    bill_to_content = [
        Paragraph("<b>BILL TO:</b>", meta_label),
        Paragraph(bill_to, body_style),
    ]
    story.append(Table([[bill_to_content]], colWidths=[530]))
    story.append(Spacer(1, 15))

    # Line Items Table
    table_data = [
        [
            Paragraph("<b>Description</b>", bold_body_style),
            Paragraph("<b>Qty</b>", bold_body_style),
            Paragraph("<b>Unit Price</b>", bold_body_style),
            Paragraph("<b>Amount</b>", bold_body_style),
        ]
    ]

    for item in line_items:
        qty_str = str(item.get("quantity", 1)) if item.get("quantity") is not None else ""
        price_str = f"{curr_sym}{item.get('unit_price', 0.0):,.2f}" if item.get("unit_price") is not None else ""
        amt_str = f"{curr_sym}{item.get('amount', 0.0):,.2f}" if item.get("amount") is not None else ""
        table_data.append([
            Paragraph(item.get("description", "Item"), body_style),
            Paragraph(qty_str, body_style),
            Paragraph(price_str, body_style),
            Paragraph(amt_str, bold_body_style),
        ])

    items_table = Table(table_data, colWidths=[270, 60, 100, 100])
    items_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f1f5f9")),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
    ]))
    story.append(items_table)
    story.append(Spacer(1, 15))

    # Summary Totals Table
    sub_str = f"{curr_sym}{subtotal:,.2f}" if subtotal is not None else "N/A"
    tax_str = f"{curr_sym}{tax_amount:,.2f}" if tax_amount is not None else "N/A"
    tot_str = f"{curr_sym}{total_amount:,.2f}" if total_amount is not None else "N/A"

    totals_data = [
        [Paragraph("<b>Subtotal:</b>", body_style), Paragraph(sub_str, bold_body_style)],
        [Paragraph("<b>Tax / VAT:</b>", body_style), Paragraph(tax_str, body_style)],
        [Paragraph("<b>Total Amount Due:</b>", ParagraphStyle("TotLabel", parent=bold_body_style, fontSize=11, textColor=colors.HexColor("#0f172a"))),
         Paragraph(tot_str, ParagraphStyle("TotVal", parent=bold_body_style, fontSize=11, textColor=colors.HexColor("#0f172a")))],
    ]
    totals_table = Table(totals_data, colWidths=[150, 100])
    totals_table.setStyle(TableStyle([
        ("ALIGN", (0, 0), (-1, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("LINEABOVE", (0, 2), (1, 2), 1, colors.HexColor("#0f172a")),
    ]))

    # Wrap totals aligned to right
    summary_wrapper = Table([["", totals_table]], colWidths=[280, 250])
    summary_wrapper.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ALIGN", (1, 0), (1, 0), "RIGHT"),
    ]))
    story.append(summary_wrapper)
    story.append(Spacer(1, 25))

    # Footer notes
    story.append(Paragraph(f"<b>Notes:</b> {notes}", body_style))
    doc.build(story)


def generate_all_sample_invoices(output_dir: str):
    """Generate the full test suite of realistic PDFs."""
    os.makedirs(output_dir, exist_ok=True)
    bill_to_address = "Acme Global Enterprises Inc.<br/>Accounts Payable Department<br/>100 Technology Plaza, Suite 400<br/>San Francisco, CA 94105"

    # 1. Happy Path: Matches PO-2026-101 exactly ($5,000.00)
    create_invoice_pdf(
        file_path=os.path.join(output_dir, "01_happy_path_apex.pdf"),
        vendor_name="Apex Cloud Solutions LLC",
        vendor_address="100 Montgomery St, Suite 1200<br/>San Francisco, CA 94104",
        vendor_tax_id="84-1234567",
        invoice_number="INV-2026-001",
        invoice_date="2026-02-15",
        due_date="2026-03-15",
        po_reference="PO-2026-101",
        bill_to=bill_to_address,
        line_items=[
            {"description": "Managed Cloud Hosting Tier 3", "quantity": 1, "unit_price": 4500.00, "amount": 4500.00},
            {"description": "Standard Support Package", "quantity": 1, "unit_price": 500.00, "amount": 500.00},
        ],
        subtotal=5000.00,
        tax_amount=0.00,
        total_amount=5000.00,
    )

    # 2. Edge Case 1: Duplicate Submission (Original and Duplicate with renamed file)
    create_invoice_pdf(
        file_path=os.path.join(output_dir, "02_duplicate_original_glp.pdf"),
        vendor_name="Global Logistics Partners",
        vendor_address="450 Harbor Boulevard<br/>Long Beach, CA 90802",
        vendor_tax_id="33-4567890",
        invoice_number="INV-GLP-8801",
        invoice_date="2026-02-05",
        due_date="2026-03-05",
        po_reference="PO-2026-103",
        bill_to=bill_to_address,
        line_items=[
            {"description": "Q1 Freight Shipping Services", "quantity": 4, "unit_price": 2100.00, "amount": 8400.00},
        ],
        subtotal=8400.00,
        tax_amount=0.00,
        total_amount=8400.00,
    )
    # Renamed duplicate file with same invoice number and content
    create_invoice_pdf(
        file_path=os.path.join(output_dir, "02_duplicate_resubmission_glp_renamed.pdf"),
        vendor_name="Global Logistics Partners",
        vendor_address="450 Harbor Boulevard<br/>Long Beach, CA 90802",
        vendor_tax_id="33-4567890",
        invoice_number="INV-GLP-8801",
        invoice_date="2026-02-05",
        due_date="2026-03-05",
        po_reference="PO-2026-103",
        bill_to=bill_to_address,
        line_items=[
            {"description": "Q1 Freight Shipping Services", "quantity": 4, "unit_price": 2100.00, "amount": 8400.00},
        ],
        subtotal=8400.00,
        tax_amount=0.00,
        total_amount=8400.00,
        notes="Customer requested duplicate copy for accounts payable records.",
    )

    # 3. Edge Case 2: Multiple Invoices Against One PO (Split PO PO-2026-102 Total: $12,500.00)
    # Milestone 1: $5,000.00
    create_invoice_pdf(
        file_path=os.path.join(output_dir, "03a_split_po_milestone1_datacore.pdf"),
        vendor_name="Datacore Infrastructure Inc.",
        vendor_address="88 Silicon Way<br/>Austin, TX 78701",
        vendor_tax_id="77-9876543",
        invoice_number="INV-DC-901",
        invoice_date="2026-01-25",
        due_date="2026-02-25",
        po_reference="PO-2026-102",
        bill_to=bill_to_address,
        line_items=[
            {"description": "Server Rack Hardware Delivery (Milestone 1)", "quantity": 1, "unit_price": 5000.00, "amount": 5000.00},
        ],
        subtotal=5000.00,
        tax_amount=0.00,
        total_amount=5000.00,
        notes="Partial delivery against PO-2026-102. Remaining balance $7,500.00.",
    )
    # Milestone 2: $7,500.00
    create_invoice_pdf(
        file_path=os.path.join(output_dir, "03b_split_po_milestone2_datacore.pdf"),
        vendor_name="Datacore Infrastructure Inc.",
        vendor_address="88 Silicon Way<br/>Austin, TX 78701",
        vendor_tax_id="77-9876543",
        invoice_number="INV-DC-902",
        invoice_date="2026-02-10",
        due_date="2026-03-10",
        po_reference="PO-2026-102",
        bill_to=bill_to_address,
        line_items=[
            {"description": "Server Rack Hardware Delivery (Milestone 2 Final)", "quantity": 1, "unit_price": 5000.00, "amount": 5000.00},
            {"description": "Network Switch Installation", "quantity": 1, "unit_price": 2500.00, "amount": 2500.00},
        ],
        subtotal=7500.00,
        tax_amount=0.00,
        total_amount=7500.00,
        notes="Final fulfillment for PO-2026-102.",
    )
    # Overdraft Invoice: $3,000.00 against depleted PO
    create_invoice_pdf(
        file_path=os.path.join(output_dir, "03c_split_po_overdraft_datacore.pdf"),
        vendor_name="Datacore Infrastructure Inc.",
        vendor_address="88 Silicon Way<br/>Austin, TX 78701",
        vendor_tax_id="77-9876543",
        invoice_number="INV-DC-903",
        invoice_date="2026-02-20",
        due_date="2026-03-20",
        po_reference="PO-2026-102",
        bill_to=bill_to_address,
        line_items=[
            {"description": "Unplanned Additional Cabling & Rerouting", "quantity": 1, "unit_price": 3000.00, "amount": 3000.00},
        ],
        subtotal=3000.00,
        tax_amount=0.00,
        total_amount=3000.00,
        notes="Out of scope additional work billed to PO-2026-102.",
    )

    # 4. Edge Case 3: Amount Discrepancy & Tolerance Boundary against PO-2026-101 ($5,000.00)
    # 4a: Within tolerance ($5,035.00 vs $5,000.00 -> +$35.00, allowable is $50.00)
    create_invoice_pdf(
        file_path=os.path.join(output_dir, "04a_within_tolerance_apex.pdf"),
        vendor_name="Apex Cloud Solutions LLC",
        vendor_address="100 Montgomery St, Suite 1200<br/>San Francisco, CA 94104",
        vendor_tax_id="84-1234567",
        invoice_number="INV-2026-002",
        invoice_date="2026-02-18",
        due_date="2026-03-18",
        po_reference="PO-2026-101",
        bill_to=bill_to_address,
        line_items=[
            {"description": "Managed Cloud Hosting Tier 3", "quantity": 1, "unit_price": 4500.00, "amount": 4500.00},
            {"description": "Standard Support Package", "quantity": 1, "unit_price": 500.00, "amount": 500.00},
            {"description": "Data Transfer Overage", "quantity": 1, "unit_price": 35.00, "amount": 35.00},
        ],
        subtotal=5035.00,
        tax_amount=0.00,
        total_amount=5035.00,
        notes="Overage within allowable contractual variance threshold.",
    )
    # 4b: Material Discrepancy Exceeding Tolerance ($5,450.00 vs $5,000.00 -> +$450.00 / 9%)
    create_invoice_pdf(
        file_path=os.path.join(output_dir, "04b_exceeds_tolerance_apex.pdf"),
        vendor_name="Apex Cloud Solutions LLC",
        vendor_address="100 Montgomery St, Suite 1200<br/>San Francisco, CA 94104",
        vendor_tax_id="84-1234567",
        invoice_number="INV-2026-003",
        invoice_date="2026-02-22",
        due_date="2026-03-22",
        po_reference="PO-2026-101",
        bill_to=bill_to_address,
        line_items=[
            {"description": "Managed Cloud Hosting Tier 3", "quantity": 1, "unit_price": 4500.00, "amount": 4500.00},
            {"description": "Premium Dedicated Support Add-on", "quantity": 1, "unit_price": 950.00, "amount": 950.00},
        ],
        subtotal=5450.00,
        tax_amount=0.00,
        total_amount=5450.00,
        notes="Includes unapproved premium support tier add-on.",
    )

    # 5. Edge Case 4: Missing or Unreliable Data (Missing Invoice Number and Total)
    create_invoice_pdf(
        file_path=os.path.join(output_dir, "05_missing_invoice_number_apex.pdf"),
        vendor_name="Apex Cloud Solutions LLC",
        vendor_address="100 Montgomery St, Suite 1200<br/>San Francisco, CA 94104",
        vendor_tax_id="84-1234567",
        invoice_number="",  # MISSING INVOICE NUMBER
        invoice_date="2026-02-25",
        due_date="2026-03-25",
        po_reference="PO-2026-101",
        bill_to=bill_to_address,
        line_items=[
            {"description": "Managed Cloud Hosting Tier 3", "quantity": 1, "unit_price": 4500.00, "amount": 4500.00},
        ],
        subtotal=4500.00,
        tax_amount=0.00,
        total_amount=4500.00,
        notes="Draft invoice statement without formal invoice numbering.",
    )

    # 6. Edge Case 5: Blocked / Unapproved Vendor
    create_invoice_pdf(
        file_path=os.path.join(output_dir, "06_blocked_vendor_blacklisted.pdf"),
        vendor_name="Blacklisted Supply Co.",
        vendor_address="12 Suspicious Blvd<br/>Chicago, IL 60601",
        vendor_tax_id="99-0001112",
        invoice_number="INV-BLK-404",
        invoice_date="2026-02-12",
        due_date="2026-03-12",
        po_reference="PO-2026-105",
        bill_to=bill_to_address,
        line_items=[
            {"description": "Unverified Office Supplies", "quantity": 1, "unit_price": 3200.00, "amount": 3200.00},
        ],
        subtotal=3200.00,
        tax_amount=0.00,
        total_amount=3200.00,
        notes="Payment freeze in place by procurement risk management.",
    )

    print(f"Successfully generated all sample invoice PDFs in: {output_dir}")


if __name__ == "__main__":
    target_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "sample_invoices")
    generate_all_sample_invoices(target_dir)
