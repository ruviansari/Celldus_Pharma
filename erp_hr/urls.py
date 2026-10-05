from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import EmployeeViewSet, AttendanceRecordViewSet, LeaveApplicationViewSet

router = DefaultRouter()
router.register(r'employees', EmployeeViewSet, basename='employee')
router.register(r'attendance', AttendanceRecordViewSet, basename='attendance')
router.register(r'leaves', LeaveApplicationViewSet, basename='leave')

urlpatterns = [
    path('', include(router.urls)),
]
