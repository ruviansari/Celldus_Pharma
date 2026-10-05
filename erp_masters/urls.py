from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    UnitOfMeasureViewSet, UOMConversionViewSet, WarehouseViewSet, StorageBinViewSet,
    ItemMasterViewSet, SupplierMasterViewSet, CustomerMasterViewSet,
    QualitySpecificationViewSet, SpecificationParameterViewSet,
    BOMHeaderViewSet, BOMLineViewSet
)

router = DefaultRouter()
router.register(r'uoms', UnitOfMeasureViewSet, basename='uom')
router.register(r'conversions', UOMConversionViewSet, basename='uom-conversion')
router.register(r'warehouses', WarehouseViewSet, basename='warehouse')
router.register(r'bins', StorageBinViewSet, basename='storage-bin')
router.register(r'items', ItemMasterViewSet, basename='item-master')
router.register(r'suppliers', SupplierMasterViewSet, basename='supplier-master')
router.register(r'customers', CustomerMasterViewSet, basename='customer-master')
router.register(r'specifications', QualitySpecificationViewSet, basename='quality-spec')
router.register(r'spec-parameters', SpecificationParameterViewSet, basename='spec-parameter')
router.register(r'boms', BOMHeaderViewSet, basename='bom-header')
router.register(r'bom-lines', BOMLineViewSet, basename='bom-line')

urlpatterns = [
    path('', include(router.urls)),
]
