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
