from django.contrib import admin
from .models import (
    UnitOfMeasure, UOMConversion, Warehouse, StorageBin,
    ItemMaster, SupplierMaster, CustomerMaster,
    QualitySpecification, SpecificationParameter,
    BOMHeader, BOMLine
)


@admin.register(UnitOfMeasure)
class UnitOfMeasureAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'symbol', 'is_discrete')


@admin.register(Warehouse)
class WarehouseAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'branch', 'controlled_access', 'temperature_min', 'temperature_max')


@admin.register(StorageBin)
class StorageBinAdmin(admin.ModelAdmin):
    list_display = ('warehouse', 'zone', 'bin_code', 'capacity_kg')
    list_filter = ('warehouse', 'zone')


@admin.register(ItemMaster)
class ItemMasterAdmin(admin.ModelAdmin):
    list_display = ('item_code', 'name', 'item_type', 'base_uom', 'storage_condition', 'shelf_life_days', 'active_flag')
    list_filter = ('item_type', 'storage_condition', 'active_flag')
    search_fields = ('item_code', 'name', 'generic_name')


@admin.register(SupplierMaster)
class SupplierMasterAdmin(admin.ModelAdmin):
    list_display = ('supplier_code', 'legal_name', 'status', 'city', 'phone', 'gmp_certificate_no')
    list_filter = ('status',)
    search_fields = ('supplier_code', 'legal_name', 'gstin')


@admin.register(CustomerMaster)
class CustomerMasterAdmin(admin.ModelAdmin):
    list_display = ('customer_code', 'name', 'customer_type', 'credit_limit', 'current_balance', 'credit_hold')
    list_filter = ('customer_type', 'credit_hold')
    search_fields = ('customer_code', 'name', 'drug_license_20b')


class BOMLineInline(admin.TabularInline):
    model = BOMLine
    extra = 1


@admin.register(BOMHeader)
class BOMHeaderAdmin(admin.ModelAdmin):
    list_display = ('bom_code', 'product', 'version', 'batch_size', 'batch_uom', 'status', 'effective_from')
    list_filter = ('status',)
    inlines = [BOMLineInline]


class SpecificationParameterInline(admin.TabularInline):
    model = SpecificationParameter
    extra = 1


@admin.register(QualitySpecification)
class QualitySpecificationAdmin(admin.ModelAdmin):
    list_display = ('spec_code', 'item', 'version', 'pharmacopoeia', 'is_approved', 'effective_date')
    list_filter = ('pharmacopoeia', 'is_approved')
    inlines = [SpecificationParameterInline]
