from django.contrib import admin
from .models import ProductionOrder, BatchMaterialConsumption, BatchProcessStep


class BatchMaterialConsumptionInline(admin.TabularInline):
    model = BatchMaterialConsumption
    extra = 1


class BatchProcessStepInline(admin.TabularInline):
    model = BatchProcessStep
    extra = 1


@admin.register(ProductionOrder)
class ProductionOrderAdmin(admin.ModelAdmin):
    list_display = ('document_no', 'batch_no', 'product', 'planned_qty', 'actual_produced_qty', 'yield_percentage', 'status')
    list_filter = ('status',)
    search_fields = ('document_no', 'batch_no', 'product__name')
    inlines = [BatchMaterialConsumptionInline, BatchProcessStepInline]
