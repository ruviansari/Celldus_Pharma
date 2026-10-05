from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import InventoryLotViewSet, StockLedgerReadOnlyViewSet, CycleCountSessionViewSet

router = DefaultRouter()
router.register(r'lots', InventoryLotViewSet, basename='inventory-lot')
router.register(r'stock-ledger', StockLedgerReadOnlyViewSet, basename='stock-ledger')
router.register(r'cycle-counts', CycleCountSessionViewSet, basename='cycle-count')

urlpatterns = [
    path('', include(router.urls)),
]
