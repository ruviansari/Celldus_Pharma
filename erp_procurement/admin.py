from django.contrib import admin
from .models import (
    PurchaseRequisition, PurchaseRequisitionLine,
    PurchaseOrder, PurchaseOrderLine,
    GoodsReceiptNote, GoodsReceiptNoteLine
)


class PurchaseOrderLineInline(admin.TabularInline):
    model = PurchaseOrderLine
    extra = 1


@admin.register(PurchaseOrder)
class PurchaseOrderAdmin(admin.ModelAdmin):
    list_display = ('document_no', 'supplier', 'order_date', 'expected_delivery_date', 'grand_total', 'status')
    list_filter = ('status',)
    search_fields = ('document_no', 'supplier__legal_name')
    inlines = [PurchaseOrderLineInline]


class GoodsReceiptNoteLineInline(admin.TabularInline):
    model = GoodsReceiptNoteLine
    extra = 1


@admin.register(GoodsReceiptNote)
class GoodsReceiptNoteAdmin(admin.ModelAdmin):
    list_display = ('document_no', 'po', 'supplier', 'warehouse', 'status', 'receipt_date')
    list_filter = ('status',)
    search_fields = ('document_no', 'delivery_challan_no')
    inlines = [GoodsReceiptNoteLineInline]
