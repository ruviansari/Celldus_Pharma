from django.contrib import admin
from .models import ChartOfAccount, JournalEntry, JournalLine, ExpenseClaim


@admin.register(ChartOfAccount)
class ChartOfAccountAdmin(admin.ModelAdmin):
    list_display = ('account_code', 'name', 'account_type', 'current_balance')
    list_filter = ('account_type',)
    search_fields = ('account_code', 'name')


class JournalLineInline(admin.TabularInline):
    model = JournalLine
    extra = 2


@admin.register(JournalEntry)
class JournalEntryAdmin(admin.ModelAdmin):
    list_display = ('document_no', 'entry_date', 'total_debit', 'total_credit', 'status')
    list_filter = ('status',)
    search_fields = ('document_no', 'description')
    inlines = [JournalLineInline]


@admin.register(ExpenseClaim)
class ExpenseClaimAdmin(admin.ModelAdmin):
    list_display = ('document_no', 'payee', 'category', 'amount', 'payment_mode', 'status', 'expense_date')
    list_filter = ('status', 'payment_mode', 'category')
    search_fields = ('document_no', 'payee', 'invoice_reference')
