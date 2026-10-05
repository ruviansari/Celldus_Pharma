from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import ProductionOrderViewSet, BatchMaterialConsumptionViewSet, BatchProcessStepViewSet

router = DefaultRouter()
router.register(r'orders', ProductionOrderViewSet, basename='production-order')
router.register(r'consumptions', BatchMaterialConsumptionViewSet, basename='batch-consumption')
router.register(r'steps', BatchProcessStepViewSet, basename='batch-step')

urlpatterns = [
    path('', include(router.urls)),
]
