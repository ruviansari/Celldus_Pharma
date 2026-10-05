from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    QCInspectionRequestViewSet, QCTestResultViewSet,
    QualityDeviationViewSet, ProductRecallViewSet
)

router = DefaultRouter()
router.register(r'inspections', QCInspectionRequestViewSet, basename='qc-inspection')
router.register(r'test-results', QCTestResultViewSet, basename='test-result')
router.register(r'deviations', QualityDeviationViewSet, basename='deviation')
router.register(r'recalls', ProductRecallViewSet, basename='product-recall')

urlpatterns = [
    path('', include(router.urls)),
]
