import uuid
from decimal import Decimal
from django.db import models, transaction
from django.conf import settings
from django.utils import timezone
from django.core.validators import MinValueValidator
from django.core.exceptions import ValidationError
from erp_core.models import ERPBaseModel, ERPDocumentModel, DocumentSequence


class ChartOfAccount(ERPBaseModel):
    """
    Standard Financial Chart of Accounts (Asset, Liability, Equity, Revenue, Expense).
    """
    ACCOUNT_TYPE_CHOICES = (
        ('ASSET', 'Asset (Cash, Bank, Inventory, AR)'),
        ('LIABILITY', 'Liability (AP, Taxes Payable, Loans)'),
        ('EQUITY', 'Equity (Capital, Retained Earnings)'),
        ('REVENUE', 'Revenue (Domestic Sales, Export Sales)'),
        ('EXPENSE', 'Expense (COGS, Raw Material, Operating, Payroll)'),
    )

    account_code = models.CharField(max_length=30, unique=True)
    name = models.CharField(max_length=150)
    account_type = models.CharField(max_length=20, choices=ACCOUNT_TYPE_CHOICES)
    parent = models.ForeignKey('self', null=True, blank=True, on_delete=models.SET_NULL, related_name='sub_accounts')
    current_balance = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal('0.00'))

    def __str__(self):
        return f"[{self.account_code}] {self.name} ({self.account_type})"


class JournalEntry(ERPDocumentModel):
    """
    General Ledger Double-Entry Journal.
    Enforces that Total Debits == Total Credits on posting.
    """
    STATUS_CHOICES = (
        ('DRAFT', 'Draft'),
        ('POSTED', 'Posted to General Ledger'),
        ('REVERSED', 'Reversed by Correction Journal'),
    )

    entry_date = models.DateField(default=timezone.now)
    description = models.TextField()
    total_debit = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal('0.00'))
    total_credit = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal('0.00'))
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='DRAFT', db_index=True)

    def clean(self):
        super().clean()
        if self.status == 'POSTED':
            if self.total_debit != self.total_credit:
                raise ValidationError({
                    'total_debit': f"Double-entry imbalance! Debits (₹{self.total_debit}) must equal Credits (₹{self.total_credit}) before posting.",
                    'total_credit': f"Double-entry imbalance! Debits (₹{self.total_debit}) must equal Credits (₹{self.total_credit}) before posting."
                })
            if self.total_debit <= Decimal('0.00'):
                raise ValidationError({
                    'total_debit': "Posted journal entry must have a total debit/credit greater than zero."
                })

    def save(self, *args, **kwargs):
        self.clean()
        if not self.document_no:
            self.document_no = DocumentSequence.get_next_number('JV', self.branch)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.document_no} - {self.entry_date} (₹{self.total_debit}) [{self.status}]"


class JournalLine(ERPBaseModel):
    journal = models.ForeignKey(JournalEntry, on_delete=models.CASCADE, related_name='lines')
    account = models.ForeignKey(ChartOfAccount, on_delete=models.PROTECT, related_name='journal_lines')
    debit = models.DecimalField(max_digits=16, decimal_places=2, default=Decimal('0.00'), validators=[MinValueValidator(Decimal('0.00'))])
    credit = models.DecimalField(max_digits=16, decimal_places=2, default=Decimal('0.00'), validators=[MinValueValidator(Decimal('0.00'))])
    narration = models.CharField(max_length=255, blank=True)

    def clean(self):
        super().clean()
        if self.debit > Decimal('0.00') and self.credit > Decimal('0.00'):
            raise ValidationError("A single journal line cannot contain both Debit and Credit amounts.")
        if self.debit == Decimal('0.00') and self.credit == Decimal('0.00'):
            raise ValidationError("Journal line must have either a Debit or Credit amount greater than zero.")

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.account.name}: Dr ₹{self.debit} / Cr ₹{self.credit}"


class ExpenseCategory(ERPBaseModel):
    """
    Pharma Enterprise Expense Categories with General Ledger mapping.
    """
    name = models.CharField(max_length=120, unique=True)
    code = models.CharField(max_length=30, unique=True)
    gl_account = models.ForeignKey(ChartOfAccount, on_delete=models.SET_NULL, null=True, blank=True, related_name='expense_categories')
    max_limit_per_claim = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'), help_text="0 for no upper cap")
    requires_receipt_above = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('250.00'))
    is_ucpmp_regulated = models.BooleanField(default=False, help_text="Pharma marketing & doctor interaction regulatory restriction")
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name_plural = "Expense Categories"
        ordering = ['code']

    def __str__(self):
        return f"[{self.code}] {self.name}"


class ExpenseSubCategory(ERPBaseModel):
    category = models.ForeignKey(ExpenseCategory, on_delete=models.CASCADE, related_name='subcategories')
    name = models.CharField(max_length=120)
    daily_rate_cap = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name_plural = "Expense Subcategories"
        unique_together = ('category', 'name')

    def __str__(self):
        return f"{self.category.name} - {self.name}"


class ExpenseClaim(ERPDocumentModel):
    """
    Commercial, Administrative, and Plant Expense Voucher with 2-Tier Approval & GL Posting.
    """
    STATUS_CHOICES = (
        ('DRAFT', 'Draft'),
        ('SUBMITTED', 'Submitted for Manager Review'),
        ('UNDER_REVIEW', 'Under Accounts Audit'),
        ('APPROVED', 'Approved for Payment'),
        ('PAID', 'Disbursed / Reimbursed'),
        ('REJECTED', 'Rejected'),
    )

    PAYMENT_MODE_CHOICES = (
        ('BANK', 'Bank Transfer / NEFT / RTGS'),
        ('UPI', 'UPI Payment'),
        ('CASH', 'Petty Cash Voucher'),
        ('CHEQUE', 'Company Cheque'),
    )

    employee = models.ForeignKey('erp_hr.Employee', null=True, blank=True, on_delete=models.SET_NULL, related_name='expense_claims')
    payee = models.CharField(max_length=150)
    category = models.CharField(max_length=100, blank=True, help_text="Legacy / textual category")
    expense_category = models.ForeignKey(ExpenseCategory, null=True, blank=True, on_delete=models.SET_NULL, related_name='claims')
    sub_category = models.ForeignKey(ExpenseSubCategory, null=True, blank=True, on_delete=models.SET_NULL, related_name='claims')

    expense_date = models.DateField(default=timezone.now, db_index=True)
    business_purpose = models.TextField(blank=True, help_text="Business justification / Tour or Plant purpose")

    # Financial Breakdown
    base_amount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'))
    tax_amount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'), help_text="Input GST (CGST+SGST/IGST)")
    amount = models.DecimalField(max_digits=14, decimal_places=2, validators=[MinValueValidator(Decimal('0.01'))], help_text="Total Claim Amount")

    # Payment & GST Compliance
    payment_mode = models.CharField(max_length=50, default='BANK', choices=PAYMENT_MODE_CHOICES)
    vendor_name = models.CharField(max_length=150, blank=True)
    vendor_gstin = models.CharField(max_length=20, blank=True)
    invoice_reference = models.CharField(max_length=100, blank=True)

    # Anti-Fraud & Duplicate Prevention
    claim_fingerprint = models.CharField(max_length=64, blank=True, db_index=True, help_text="SHA-256 duplicate fingerprint")

    # 2-Tier Approval Attributes
    manager_approver = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='manager_approved_expenses')
    manager_approved_at = models.DateTimeField(null=True, blank=True)
    manager_remarks = models.TextField(blank=True)

    finance_approver = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='finance_approved_expenses')
    finance_approved_at = models.DateTimeField(null=True, blank=True)
    finance_remarks = models.TextField(blank=True)

    # Settlement / Disbursement Reference
    payment_utr = models.CharField(max_length=100, blank=True, help_text="Bank UTR / Transaction ID")
    payment_date = models.DateField(null=True, blank=True)
    linked_journal = models.OneToOneField(JournalEntry, null=True, blank=True, on_delete=models.SET_NULL, related_name='expense_claim_source')

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='DRAFT', db_index=True)

    def save(self, *args, **kwargs):
        if not self.base_amount or self.base_amount == Decimal('0.00'):
            self.base_amount = self.amount - (self.tax_amount or Decimal('0.00'))
        if not self.document_no:
            self.document_no = DocumentSequence.get_next_number('EXP', self.branch)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.document_no} - {self.payee}: ₹{self.amount} ({self.status})"


class ExpenseAttachment(ERPBaseModel):
    """
    Receipt, GST Tax Invoice, or Travel Ticket Document.
    """
    expense = models.ForeignKey(ExpenseClaim, on_delete=models.CASCADE, related_name='attachments')
    file = models.FileField(upload_to='expenses/%Y/%m/')
    filename = models.CharField(max_length=255)
    file_size = models.PositiveIntegerField(default=0, help_text="File size in bytes")
    file_hash = models.CharField(max_length=64, blank=True, db_index=True, help_text="SHA256 duplicate hash")
    description = models.CharField(max_length=255, blank=True)

    def __str__(self):
        return f"{self.filename} ({self.expense.document_no})"
