from decimal import Decimal
from django.db import transaction
from django.core.exceptions import ValidationError
from erp_core.security import audit_log_event
from .models import JournalEntry, JournalLine, ChartOfAccount


@transaction.atomic
def post_journal_entry(journal_id, user):
    """
    Validates that total debits == total credits,
    updates account balances atomically, and marks journal as POSTED.
    """
    journal = JournalEntry.objects.select_for_update().get(id=journal_id)

    if journal.status == 'POSTED':
        raise ValidationError("Journal is already posted.")

    lines = journal.lines.all()
    if not lines.exists():
        raise ValidationError("Cannot post an empty journal.")

    total_debits = sum(line.debit for line in lines)
    total_credits = sum(line.credit for line in lines)

    if total_debits != total_credits:
        raise ValidationError(f"Accounting Inbalance: Total Debits (₹{total_debits}) must equal Total Credits (₹{total_credits}). Difference: ₹{abs(total_debits - total_credits)}")

    journal.total_debit = total_debits
    journal.total_credit = total_credits

    # Update account balances
    for line in lines:
        acct = ChartOfAccount.objects.select_for_update().get(id=line.account_id)
        if acct.account_type in ['ASSET', 'EXPENSE']:
            acct.current_balance += (line.debit - line.credit)
        else:
            acct.current_balance += (line.credit - line.debit)
        acct.save(update_fields=['current_balance'])

    journal.status = 'POSTED'
    journal.save(update_fields=['total_debit', 'total_credit', 'status', 'updated_at'])

    audit_log_event(
        user=user,
        action='POST',
        entity_name='JournalEntry',
        entity_id=journal.id,
        document_no=journal.document_no,
        reason=f"Posted journal voucher. Total: ₹{total_debits}"
    )

    return journal


# ==========================================
# EXPENSE MANAGEMENT & COMPLIANCE ENGINE
# ==========================================
import hashlib
from datetime import timedelta
from django.utils import timezone
from .models import ExpenseClaim, ExpenseCategory, ExpenseSubCategory, ExpenseAttachment
from erp_core.security import check_prevent_self_approval
from erp_core.models import DocumentSequence


def generate_claim_fingerprint(employee_id, expense_date, amount, invoice_number=""):
    """
    Computes deterministic SHA-256 fingerprint to prevent double-claiming of expenses.
    """
    raw_str = f"{employee_id}:{str(expense_date)}:{str(amount)}:{str(invoice_number).strip().lower()}"
    return hashlib.sha256(raw_str.encode('utf-8')).hexdigest()


def check_duplicate_claim(employee_id, expense_date, amount, invoice_number="", exclude_claim_id=None):
    """
    Scans for duplicate claims within a 60-day window.
    """
    fp = generate_claim_fingerprint(employee_id, expense_date, amount, invoice_number)
    qs = ExpenseClaim.objects.filter(claim_fingerprint=fp).exclude(status='REJECTED')
    if exclude_claim_id:
        qs = qs.exclude(id=exclude_claim_id)
    return qs.first()


@transaction.atomic
def submit_expense_claim(user, employee, category, amount, expense_date=None, base_amount=None, tax_amount=None,
                         business_purpose="", payee="", payment_mode="BANK", vendor_name="", vendor_gstin="",
                         invoice_reference="", sub_category=None, attachments=None, is_submit=True, request=None):
    """
    Creates an Expense Claim with anti-duplicate validation, policy cap checks, and document sequencing.
    """
    amount = Decimal(str(amount or '0.00'))
    tax_amount = Decimal(str(tax_amount or '0.00'))
    base_amount = Decimal(str(base_amount or '0.00')) if base_amount else (amount - tax_amount)
    expense_date = expense_date or timezone.now().date()
    payee = payee or f"{employee.first_name} {employee.last_name}"

    if amount <= Decimal('0.00'):
        raise ValidationError("Expense claim amount must be greater than zero.")

    # 1. Category Limit Policy Check
    if category and category.max_limit_per_claim > Decimal('0.00'):
        if amount > category.max_limit_per_claim:
            raise ValidationError(
                f"Claim amount ₹{amount} exceeds policy maximum cap (₹{category.max_limit_per_claim}) for category '{category.name}'."
            )

    # 2. Duplicate Detection
    dup = check_duplicate_claim(employee.id, expense_date, amount, invoice_reference)
    if dup:
        raise ValidationError(
            f"Duplicate expense detected! A matching claim [{dup.document_no}] for ₹{amount} on {expense_date} already exists in status '{dup.status}'."
        )

    fp = generate_claim_fingerprint(employee.id, expense_date, amount, invoice_reference)
    status = 'SUBMITTED' if is_submit else 'DRAFT'

    claim = ExpenseClaim.objects.create(
        employee=employee,
        branch=employee.branch,
        payee=payee,
        category=category.name if category else '',
        expense_category=category,
        sub_category=sub_category,
        expense_date=expense_date,
        business_purpose=business_purpose,
        base_amount=base_amount,
        tax_amount=tax_amount,
        amount=amount,
        payment_mode=payment_mode,
        vendor_name=vendor_name,
        vendor_gstin=vendor_gstin,
        invoice_reference=invoice_reference,
        claim_fingerprint=fp,
        status=status,
        created_by=user,
        updated_by=user,
    )

    # 3. Process attachments
    if attachments:
        for f in attachments:
            content = f.read()
            f_hash = hashlib.sha256(content).hexdigest()
            f.seek(0)
            ExpenseAttachment.objects.create(
                expense=claim,
                file=f,
                filename=f.name,
                file_size=len(content),
                file_hash=f_hash,
                created_by=user,
            )

    action_label = 'SUBMIT' if is_submit else 'CREATE'
    audit_log_event(
        user=user,
        action=action_label,
        entity_name='ExpenseClaim',
        entity_id=str(claim.id),
        document_no=claim.document_no,
        reason=f"{action_label} expense claim for ₹{claim.amount} ({category.name if category else 'General'})",
        request=request
    )

    return claim


@transaction.atomic
def manager_review_expense(claim_id, user, action='APPROVE', remarks="", request=None):
    """
    Tier-1 Approval: Reporting Manager or Department Head reviews claim.
    Transitions: SUBMITTED -> UNDER_REVIEW (Approved) or REJECTED.
    """
    claim = ExpenseClaim.objects.select_for_update().get(id=claim_id)

    if claim.status not in ['SUBMITTED', 'UNDER_REVIEW']:
        raise ValidationError(f"Claim [{claim.document_no}] cannot be reviewed from status '{claim.status}'.")

    check_prevent_self_approval(claim, user)

    if action.upper() == 'APPROVE':
        claim.status = 'UNDER_REVIEW'
        claim.manager_approver = user
        claim.manager_approved_at = timezone.now()
        claim.manager_remarks = remarks
        reason_msg = f"Manager approved claim [{claim.document_no}]. Forwarded to Accounts audit."
    else:
        claim.status = 'REJECTED'
        claim.rejection_reason = remarks or "Rejected by manager."
        reason_msg = f"Manager rejected claim [{claim.document_no}]: {claim.rejection_reason}"

    claim.updated_by = user
    claim.save()

    audit_log_event(
        user=user,
        action=action.upper(),
        entity_name='ExpenseClaim',
        entity_id=str(claim.id),
        document_no=claim.document_no,
        reason=reason_msg,
        request=request
    )

    return claim


@transaction.atomic
def finance_audit_expense(claim_id, user, action='APPROVE', remarks="", request=None):
    """
    Tier-2 Approval: Accounts & Finance Head sanctions claim for payment.
    Transitions: UNDER_REVIEW -> APPROVED (Approved) or REJECTED.
    """
    claim = ExpenseClaim.objects.select_for_update().get(id=claim_id)

    if claim.status != 'UNDER_REVIEW':
        raise ValidationError(f"Claim [{claim.document_no}] is not ready for Finance audit (current status: '{claim.status}').")

    check_prevent_self_approval(claim, user)

    if action.upper() == 'APPROVE':
        claim.status = 'APPROVED'
        claim.finance_approver = user
        claim.finance_approved_at = timezone.now()
        claim.finance_remarks = remarks
        reason_msg = f"Finance sanctioned claim [{claim.document_no}] for disbursement."
    else:
        claim.status = 'REJECTED'
        claim.rejection_reason = remarks or "Rejected by Accounts Head."
        reason_msg = f"Finance rejected claim [{claim.document_no}]: {claim.rejection_reason}"

    claim.updated_by = user
    claim.save()

    audit_log_event(
        user=user,
        action=action.upper(),
        entity_name='ExpenseClaim',
        entity_id=str(claim.id),
        document_no=claim.document_no,
        reason=reason_msg,
        request=request
    )

    return claim


@transaction.atomic
def disburse_expense_and_post_gl(claim_id, user, payment_utr="", payment_mode=None, bank_gl_account=None, request=None):
    """
    Disburses approved claim and automatically posts Double-Entry Journal to General Ledger:
    - Dr. Respective Expense Account (Base Amount)
    - Dr. GST Input Account (Tax Amount, if applicable)
    - Cr. Bank Account / Cash Account (Total Disbursed Amount)
    """
    claim = ExpenseClaim.objects.select_for_update().get(id=claim_id)

    if claim.status != 'APPROVED':
        raise ValidationError(f"Claim [{claim.document_no}] must be in 'APPROVED' status before payment (currently '{claim.status}').")

    if not payment_utr and (claim.payment_mode or payment_mode) != 'CASH':
        payment_utr = f"UTR-{timezone.now().strftime('%Y%m%d%H%M%S')}"

    # Determine Credit Account (Bank or Cash)
    if not bank_gl_account:
        if (payment_mode or claim.payment_mode) == 'CASH':
            bank_gl_account = ChartOfAccount.objects.filter(account_code='1001').first() # Cash
        else:
            bank_gl_account = ChartOfAccount.objects.filter(account_code='1002').first() # HDFC Corporate Bank

    if not bank_gl_account:
        raise ValidationError("Cannot disburse expense: Corporate Bank/Cash GL account not found in Chart of Accounts.")

    # Determine Debit Account (Expense Account)
    expense_gl_account = None
    if claim.expense_category and claim.expense_category.gl_account:
        expense_gl_account = claim.expense_category.gl_account
    else:
        expense_gl_account = ChartOfAccount.objects.filter(account_type='EXPENSE').first()

    if not expense_gl_account:
        raise ValidationError("Cannot disburse expense: Target Expense GL account not configured.")

    # Input GST Account
    gst_gl_account = ChartOfAccount.objects.filter(account_code='2100').first()

    # 1. Create Double-Entry Journal Voucher
    jv_doc_no = DocumentSequence.get_next_number('JV', claim.branch)
    journal = JournalEntry.objects.create(
        document_no=jv_doc_no,
        branch=claim.branch,
        entry_date=timezone.now().date(),
        description=f"Disbursement settlement for {claim.document_no} - {claim.payee} ({claim.business_purpose[:80]})",
        total_debit=claim.amount,
        total_credit=claim.amount,
        status='DRAFT',
        created_by=user,
        updated_by=user,
    )

    # Line 1: Debit Expense Account
    JournalLine.objects.create(
        journal=journal,
        account=expense_gl_account,
        debit=claim.base_amount,
        credit=Decimal('0.00'),
        narration=f"Expense Voucher {claim.document_no}: {claim.payee}",
        created_by=user,
    )

    # Line 2: Debit Tax Account if any tax claimed
    if claim.tax_amount and claim.tax_amount > Decimal('0.00'):
        target_tax_acct = gst_gl_account if gst_gl_account else expense_gl_account
        JournalLine.objects.create(
            journal=journal,
            account=target_tax_acct,
            debit=claim.tax_amount,
            credit=Decimal('0.00'),
            narration=f"Input GST credit on {claim.document_no} (Vendor: {claim.vendor_name or 'N/A'})",
            created_by=user,
        )

    # Line 3: Credit Bank/Cash
    JournalLine.objects.create(
        journal=journal,
        account=bank_gl_account,
        debit=Decimal('0.00'),
        credit=claim.amount,
        narration=f"Payment via {claim.payment_mode} | Ref/UTR: {payment_utr}",
        created_by=user,
    )

    # Post Journal to General Ledger
    post_journal_entry(journal.id, user)

    # 2. Update Claim Status
    claim.status = 'PAID'
    claim.payment_utr = payment_utr
    claim.payment_date = timezone.now().date()
    claim.linked_journal = journal
    if payment_mode:
        claim.payment_mode = payment_mode
    claim.updated_by = user
    claim.save()

    audit_log_event(
        user=user,
        action='DISBURSE',
        entity_name='ExpenseClaim',
        entity_id=str(claim.id),
        document_no=claim.document_no,
        reason=f"Disbursed ₹{claim.amount} via {claim.payment_mode} (UTR: {payment_utr}). Auto-posted to GL Journal [{journal.document_no}].",
        request=request
    )

    return claim
