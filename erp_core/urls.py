from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from .views import BranchViewSet, ERPUserRoleViewSet, AuditLogReadOnlyViewSet, CurrentUserContextView

router = DefaultRouter()
router.register(r'branches', BranchViewSet, basename='branch')
router.register(r'roles', ERPUserRoleViewSet, basename='user-role')
router.register(r'audit-logs', AuditLogReadOnlyViewSet, basename='audit-log')

urlpatterns = [
    # JWT Authentication Endpoints
    path('auth/login/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('auth/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('auth/me/', CurrentUserContextView.as_view(), name='current_user_context'),

    # Core Router Endpoints
    path('', include(router.urls)),
]
