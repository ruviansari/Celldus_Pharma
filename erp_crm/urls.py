from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import LeadViewSet, FollowUpTaskViewSet, LeadImportBatchViewSet

router = DefaultRouter()
router.register(r'leads', LeadViewSet, basename='lead')
router.register(r'tasks', FollowUpTaskViewSet, basename='crm-task')
router.register(r'imports', LeadImportBatchViewSet, basename='lead-import')

urlpatterns = [
    path('', include(router.urls)),
]
