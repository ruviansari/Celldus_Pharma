from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import PurchaseRequisitionViewSet, PurchaseOrderViewSet, GoodsReceiptNoteViewSet

router = DefaultRouter()
router.register(r'requisitions', PurchaseRequisitionViewSet, basename='requisition')
router.register(r'purchase-orders', PurchaseOrderViewSet, basename='purchase-order')
router.register(r'grns', GoodsReceiptNoteViewSet, basename='grn')

urlpatterns = [
    path('', include(router.urls)),
]
