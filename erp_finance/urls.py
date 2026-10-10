from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import ChartOfAccountViewSet, JournalEntryViewSet, ExpenseClaimViewSet, ExpenseCategoryViewSet

router = DefaultRouter()
router.register(r'accounts', ChartOfAccountViewSet, basename='chart-account')
router.register(r'journals', JournalEntryViewSet, basename='journal-entry')
router.register(r'categories', ExpenseCategoryViewSet, basename='expense-category')
router.register(r'expenses', ExpenseClaimViewSet, basename='expense-claim')

urlpatterns = [
    path('', include(router.urls)),
]
