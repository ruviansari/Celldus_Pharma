import os
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import inch
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, KeepTogether, HRFlowable
)
from reportlab.pdfgen import canvas

class NumberedCanvas(canvas.Canvas):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_decorations(num_pages)
            super().showPage()
        super().save()

    def draw_page_decorations(self, page_count):
        self.saveState()
        self.setFont("Helvetica", 8)
        self.setFillColor(colors.HexColor("#64748b"))
        
        # Header (pages > 1)
        if self._pageNumber > 1:
            self.drawString(40, A4[1] - 30, "CELLDUS PHARMA ERP — EXPENSE TRACKER ACCESS & TESTING GUIDE")
            self.setStrokeColor(colors.HexColor("#e2e8f0"))
            self.setLineWidth(0.5)
            self.line(40, A4[1] - 34, A4[0] - 40, A4[1] - 34)

        # Footer
        self.setStrokeColor(colors.HexColor("#e2e8f0"))
        self.setLineWidth(0.5)
        self.line(40, 36, A4[0] - 40, 36)
        
        self.drawString(40, 24, "Confidential — For Internal Celldus Pharma ERP QA & Enterprise Testing Only")
        page_str = f"Page {self._pageNumber} of {page_count}"
        self.drawRightString(A4[0] - 40, 24, page_str)
        self.restoreState()


def build_pdf(filename="Celldus_Pharma_Expense_Tracker_Testing_Guide.pdf"):
    doc = SimpleDocTemplate(
        filename,
        pagesize=A4,
        leftMargin=40,
        rightMargin=40,
        topMargin=46,
        bottomMargin=46
    )

    styles = getSampleStyleSheet()

    # Custom styles
    primary_color = colors.HexColor("#0284c7")
    navy_dark = colors.HexColor("#0f172a")
    text_dark = colors.HexColor("#1e293b")
    text_muted = colors.HexColor("#64748b")
    success_color = colors.HexColor("#059669")
    accent_purple = colors.HexColor("#7c3aed")

    title_style = ParagraphStyle(
        'DocTitle',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=20,
        leading=24,
        textColor=navy_dark,
        spaceAfter=4
    )

    subtitle_style = ParagraphStyle(
        'DocSubtitle',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=10,
        leading=14,
        textColor=text_muted,
        spaceAfter=14
    )

    h1_style = ParagraphStyle(
        'Heading1_Custom',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=13,
        leading=17,
        textColor=primary_color,
        spaceBefore=12,
        spaceAfter=6
    )

    h2_style = ParagraphStyle(
        'Heading2_Custom',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=10.5,
        leading=14,
        textColor=navy_dark,
        spaceBefore=8,
        spaceAfter=4
    )

    body_style = ParagraphStyle(
        'Body_Custom',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=8.5,
        leading=12,
        textColor=text_dark
    )

    body_bold = ParagraphStyle(
        'Body_Bold',
        parent=body_style,
        fontName='Helvetica-Bold'
    )

    callout_style = ParagraphStyle(
        'Callout',
        parent=styles['Normal'],
        fontName='Helvetica-Oblique',
        fontSize=8.5,
        leading=12,
        textColor=colors.HexColor("#0369a1")
    )

    story = []

    # 1. Header Banner
    story.append(Paragraph("CELLDUS PHARMACEUTICALS ERP", ParagraphStyle('PreTitle', fontName='Helvetica-Bold', fontSize=8.5, textColor=primary_color, spaceAfter=2)))
    story.append(Paragraph("Expense Tracker & GL Integration: Access & Testing Guide", title_style))
    story.append(Paragraph("Complete Operational Manual: URL Endpoints, User Credentials, Multi-Tier Approval Lifecycle & Verification Test Cases", subtitle_style))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#0284c7"), spaceAfter=12))

    # 2. Portal URLs & Access Matrix
    story.append(Paragraph("1. Portal URLs & Login Access Matrix", h1_style))
    
    url_data = [
        [Paragraph("<b>Environment</b>", body_bold), Paragraph("<b>Target URL</b>", body_bold), Paragraph("<b>Module Path</b>", body_bold)],
        [
            Paragraph("<b>Live Cloudflare Tunnel</b>", body_style),
            Paragraph("<font color='#0284c7'><u>https://reporting-doe-telephone-engines.trycloudflare.com/dashboard/login/</u></font>", body_style),
            Paragraph("<code>/dashboard/expenses/</code>", body_style)
        ],
        [
            Paragraph("<b>Local Dev Server</b>", body_style),
            Paragraph("<font color='#0284c7'><u>http://127.0.0.1:8000/dashboard/login/</u></font>", body_style),
            Paragraph("<code>/dashboard/expenses/</code>", body_style)
        ],
        [
            Paragraph("<b>REST Swagger API Docs</b>", body_style),
            Paragraph("<font color='#0284c7'><u>http://127.0.0.1:8000/api/docs/#/erp_finance</u></font>", body_style),
            Paragraph("<code>/api/finance/expenses/</code>", body_style)
        ]
    ]

    t_url = Table(url_data, colWidths=[110, 280, 125])
    t_url.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#f1f5f9")),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    story.append(t_url)
    story.append(Spacer(1, 8))

    # 3. Test Credentials Table
    story.append(Paragraph("Verified Testing Credentials", h2_style))
    cred_data = [
        [
            Paragraph("<b>Role / Purpose</b>", body_bold),
            Paragraph("<b>Username</b>", body_bold),
            Paragraph("<b>Password</b>", body_bold),
            Paragraph("<b>Employee Code</b>", body_bold),
            Paragraph("<b>Designation</b>", body_bold)
        ],
        [
            Paragraph("<b>Staff Employee (Submitter)</b>", body_style),
            Paragraph("<code>manohar</code>", body_bold),
            Paragraph("<code>verma@123</code>", body_style),
            Paragraph("EMP-ADM-007", body_style),
            Paragraph("National Sales Director (Staff)", body_style)
        ],
        [
            Paragraph("<b>HR Submitter (Alternative)</b>", body_style),
            Paragraph("<code>anjali</code>", body_bold),
            Paragraph("<code>anjali@123</code>", body_style),
            Paragraph("EMP-HR-007", body_style),
            Paragraph("Human Resources Lead", body_style)
        ],
        [
            Paragraph("<b>Super Admin (Approver & CFO)</b>", body_style),
            Paragraph("<code>admin</code>", body_bold),
            Paragraph("<code>admin</code>", body_style),
            Paragraph("EMP-ADM-001", body_style),
            Paragraph("Executive Director (All Approvals)", body_style)
        ],
        [
            Paragraph("<b>Super Admin (Alternative)</b>", body_style),
            Paragraph("<code>superadmin</code>", body_bold),
            Paragraph("<code>superadmin123</code>", body_style),
            Paragraph("EMP-ADM-009", body_style),
            Paragraph("Super Admin", body_style)
        ]
    ]

    t_cred = Table(cred_data, colWidths=[120, 80, 85, 95, 135])
    t_cred.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#f8fafc")),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    story.append(t_cred)
    story.append(Spacer(1, 12))

    # 4. End-to-End Testing Workflow
    story.append(Paragraph("2. Complete End-to-End Testing Workflow (Step-by-Step)", h1_style))

    # Step 1
    story.append(Paragraph("<b>Step 1: Employee Creates & Submits Expense Claim</b>", h2_style))
    p1 = (
        "1. Login with Staff credentials: <b>username:</b> <code>manohar</code> | <b>password:</b> <code>verma@123</code><br/>"
        "2. Left navigation menu se <b>'Expense Tracker (GL)'</b> link par click karein.<br/>"
        "3. Top-right corner par <b>'+ New Expense Claim'</b> button click karein.<br/>"
        "4. Modal pop-up mein claim data enter karein:<br/>"
        "&nbsp;&nbsp;&nbsp;&nbsp;• <b>Category:</b> Select <i>'Field Travel & Conveyance'</i> (GL Code: 5004)<br/>"
        "&nbsp;&nbsp;&nbsp;&nbsp;• <b>Base Amount:</b> <code>2000.00</code> | <b>GST Tax Amount:</b> <code>360.00</code> (Live Total: ₹2,360.00)<br/>"
        "&nbsp;&nbsp;&nbsp;&nbsp;• <b>Vendor Name & Invoice #:</b> e.g., <i>'Indian Oil'</i>, <i>'INV-FUEL-1029'</i><br/>"
        "&nbsp;&nbsp;&nbsp;&nbsp;• <b>Paid Via:</b> <i>'Bank Transfer'</i> | <b>Receipt File:</b> Upload any sample bill/PDF (Max 5MB)<br/>"
        "&nbsp;&nbsp;&nbsp;&nbsp;• <b>Business Purpose:</b> <i>'Territory doctor clinical review tour travel expenses'</i><br/>"
        "5. Click <b>'Submit for Approval'</b>.<br/>"
        "<b>Expected Outcome:</b> Claim register mein generate hoga status <b><font color='#0284c7'>SUBMITTED (Manager Review)</font></b>."
    )
    story.append(Paragraph(p1, body_style))
    story.append(Spacer(1, 6))

    # Step 2
    story.append(Paragraph("<b>Step 2: Tier-1 Manager Review & Approval</b>", h2_style))
    p2 = (
        "1. Manohar account logout karein aur Admin account se login karein: <b>username:</b> <code>admin</code> | <b>password:</b> <code>admin</code><br/>"
        "2. <b>Expense Tracker</b> par jayein aur <b>'Approval Queue'</b> tab open karein.<br/>"
        "3. Manohar ke claim ke aage purple <b>'Review'</b> button par click karein.<br/>"
        "4. Review remarks enter karein (e.g., <i>'Tour travel verified with beat plan'</i>) aur <b>'Approve Claim'</b> click karein.<br/>"
        "<b>Expected Outcome:</b> Claim status automatically transition hokar <b><font color='#d97706'>UNDER_REVIEW (Finance Audit)</font></b> ho jayega."
    )
    story.append(Paragraph(p2, body_style))
    story.append(Spacer(1, 6))

    # Step 3
    story.append(Paragraph("<b>Step 3: Tier-2 Finance & Tax Audit Sanction</b>", h2_style))
    p3 = (
        "1. <code>admin</code> (Finance/Accounts role) session mein hi <b>'Approval Queue'</b> tab par check karein.<br/>"
        "2. Claim ke action column mein ab orange <b>'Audit'</b> button activate ho jayega.<br/>"
        "3. Click <b>'Audit'</b>: Modal Base Amount (₹2,000), GST ITC (₹360), Vendor Name aur Tax Invoice Number show karega.<br/>"
        "4. Finance remarks likhein (e.g., <i>'Tax bill verified against GSTR-2B compliance'</i>) aur <b>'Sanction Claim'</b> par click karein.<br/>"
        "<b>Expected Outcome:</b> Claim Finance audit pass karke <b><font color='#2563eb'>APPROVED (Ready to Pay)</font></b> ho jayega."
    )
    story.append(Paragraph(p3, body_style))
    story.append(Spacer(1, 6))

    # Step 4
    story.append(Paragraph("<b>Step 4: Disbursement & Automated Double-Entry General Ledger (GL) Posting</b>", h2_style))
    p4 = (
        "1. Approved claim ke aage green <b>'Disburse & GL'</b> button par click karein.<br/>"
        "2. Modal pop-up form verify karein:<br/>"
        "&nbsp;&nbsp;&nbsp;&nbsp;• <b>Disbursing Account:</b> Select <i>'1002 - HDFC Bank Corporate Current A/c'</i> (or 1001 Petty Cash)<br/>"
        "&nbsp;&nbsp;&nbsp;&nbsp;• <b>Payment UTR / Ref #:</b> Enter e.g., <code>UTR-HDFC-99182374</code><br/>"
        "&nbsp;&nbsp;&nbsp;&nbsp;• Pop-up Double-Entry GL Ledger scheme preview dikhayega:<br/>"
        "&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;<i>• DR. 5004 - Field Sales Conveyance (₹2,000.00)<br/>"
        "&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;• DR. 2100 - Input GST / Tax Receivable (₹360.00)<br/>"
        "&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;• CR. 1002 - HDFC Bank Corporate Current A/c (₹2,360.00)</i><br/>"
        "3. Click <b>'Confirm & Post GL Journal'</b>.<br/>"
        "<b>Expected Outcome:</b><br/>"
        "&nbsp;&nbsp;&nbsp;&nbsp;• Claim status green <b><font color='#059669'>PAID (Paid & GL Posted)</font></b> ho jayega.<br/>"
        "&nbsp;&nbsp;&nbsp;&nbsp;• Row ke andar live Journal Voucher link generate hoga: <code>JRN: JV-RND-BLR-2026-27-0000X</code>.<br/>"
        "&nbsp;&nbsp;&nbsp;&nbsp;• Corporate bank account current balance atomically decrement ho jayega."
    )
    story.append(Paragraph(p4, body_style))
    story.append(Spacer(1, 12))

    # 5. Security & Anti-Fraud Verification Scenarios
    story.append(Paragraph("3. Regulatory & Anti-Fraud Verification Test Cases (For QA)", h1_style))
    
    qa_data = [
        [
            Paragraph("<b>Test Case / Guardrail</b>", body_bold),
            Paragraph("<b>Tester Action</b>", body_bold),
            Paragraph("<b>Expected System Behavior & Result</b>", body_bold)
        ],
        [
            Paragraph("<b>SHA-256 Duplicate Bill Prevention</b>", body_bold),
            Paragraph("Manohar ke account se exact wahi date, amount (₹2360) aur wahi invoice reference dobara submit karein.", body_style),
            Paragraph("<font color='#dc2626'><b>BLOCKED</b></font>: System duplicate submission reject karega: <i>'Duplicate claim detected! Identical claim already registered.'</i>", body_style)
        ],
        [
            Paragraph("<b>Segregation of Duties (SOD) Self-Approval</b>", body_bold),
            Paragraph("Agar Submitter employee khud apne claim par Manager review ya Finance audit action lene ka try kare.", body_style),
            Paragraph("<font color='#dc2626'><b>BLOCKED</b></font>: 403 Forbidden trigger hoga: <i>'Segregation of Duties Violation: You cannot approve a document you created.'</i>", body_style)
        ],
        [
            Paragraph("<b>Receipt Mandate Threshold Rule</b>", body_bold),
            Paragraph("Receipt attachment blank chhod kar ₹2,000 ka bill submit karne ka try karein.", body_style),
            Paragraph("<font color='#d97706'><b>POLICY ENFORCED</b></font>: System submit nahi hone dega jab tak valid receipt attach na ho (Category threshold policy).", body_style)
        ],
        [
            Paragraph("<b>21 CFR Part 11 Audit Trail</b>", body_bold),
            Paragraph("Claim ke aage <b>Eye icon (View Details)</b> par click karein.", body_style),
            Paragraph("<font color='#059669'><b>PASS</b></font>: Complete attributable audit log visible hoga: Submitter, Submission Date, Approver, Remarks, UTR, aur GL Voucher Number.", body_style)
        ],
        [
            Paragraph("<b>Light / Dark Theme Contrast</b>", body_bold),
            Paragraph("Top header se <b>'Light Mode'</b> toggle button click karein.", body_style),
            Paragraph("<font color='#059669'><b>PASS</b></font>: Table background clean white (`#ffffff`) aur row hover soft light grey (`#f1f5f9`) render hogi.", body_style)
        ]
    ]

    t_qa = Table(qa_data, colWidths=[130, 160, 225])
    t_qa.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#f1f5f9")),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    story.append(t_qa)
    story.append(Spacer(1, 14))

    # Summary Note
    story.append(Paragraph("<b>Enterprise Regulatory Certification:</b> This Expense Management module complies with Indian GST ITC Input Credit rules, UCPMP 2024 Pharmaceutical Marketing Conduct, and 21 CFR Part 11 Electronic Records Integrity.", callout_style))

    doc.build(story, canvasmaker=NumberedCanvas)
    print(f"PDF successfully generated: {filename}")

if __name__ == '__main__':
    build_pdf()
