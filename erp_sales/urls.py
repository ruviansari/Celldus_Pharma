from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import SalesOrderViewSet, SalesDispatchInvoiceViewSet

router = DefaultRouter()
router.register(r'orders', SalesOrderViewSet, basename='sales-order')
router.register(r'invoices', SalesDispatchInvoiceViewSet, basename='sales-invoice')

urlpatterns = [
    path('', include(router.urls)),
]
