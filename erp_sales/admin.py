from django.contrib import admin
from .models import SalesOrder, SalesOrderLine, SalesOrderLotAllocation, SalesDispatchInvoice


class SalesOrderLineInline(admin.TabularInline):
    model = SalesOrderLine
    extra = 1


@admin.register(SalesOrder)
class SalesOrderAdmin(admin.ModelAdmin):
    list_display = ('document_no', 'customer', 'order_date', 'requested_delivery_date', 'grand_total', 'status')
    list_filter = ('status',)
    search_fields = ('document_no', 'customer__name')
    inlines = [SalesOrderLineInline]


@admin.register(SalesDispatchInvoice)
class SalesDispatchInvoiceAdmin(admin.ModelAdmin):
    list_display = ('document_no', 'customer', 'invoice_date', 'total_amount', 'eway_bill_no', 'is_paid')
    search_fields = ('document_no', 'customer__name', 'eway_bill_no')
