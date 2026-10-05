from django.contrib import admin
from .models import InventoryLot, StockLedger, CycleCountSession, CycleCountLine


@admin.register(InventoryLot)
class InventoryLotAdmin(admin.ModelAdmin):
    list_display = ('lot_number', 'item', 'batch_no', 'warehouse', 'status', 'quantity_on_hand', 'quantity_reserved', 'expiry_date')
    list_filter = ('status', 'warehouse')
    search_fields = ('lot_number', 'batch_no', 'item__name')


@admin.register(StockLedger)
class StockLedgerAdmin(admin.ModelAdmin):
    list_display = ('timestamp', 'transaction_type', 'document_no', 'item', 'quantity', 'uom', 'user')
    list_filter = ('transaction_type',)
    search_fields = ('document_no', 'lot__lot_number', 'item__name')
    readonly_fields = [f.name for f in StockLedger._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
