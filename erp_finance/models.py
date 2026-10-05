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


class ExpenseClaim(ERPDocumentModel):
    """
    Commercial, Administrative, and Factory Expense Voucher.
    """
    STATUS_CHOICES = (
        ('DRAFT', 'Draft'),
        ('SUBMITTED', 'Submitted for Verification'),
        ('APPROVED', 'Approved by Accounts Head'),
        ('PAID', 'Disbursed / Paid'),
        ('REJECTED', 'Rejected'),
    )

    payee = models.CharField(max_length=150)
    category = models.CharField(max_length=100, help_text="e.g. Travel, Lab Consumables, Utilities, Freight")
    expense_date = models.DateField(default=timezone.now)
    amount = models.DecimalField(max_digits=14, decimal_places=2, validators=[MinValueValidator(Decimal('0.01'))])
    tax_amount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'))
    payment_mode = models.CharField(max_length=50, default='NEFT/RTGS', choices=(('CASH', 'Cash'), ('BANK', 'Bank Transfer / NEFT'), ('UPI', 'UPI'), ('CHEQUE', 'Cheque')))
    invoice_reference = models.CharField(max_length=100, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='DRAFT', db_index=True)

    def save(self, *args, **kwargs):
        if not self.document_no:
            self.document_no = DocumentSequence.get_next_number('EXP', self.branch)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.document_no} - {self.payee}: ₹{self.amount} ({self.status})"
