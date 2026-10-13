from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    EmployeeViewSet,
    AttendanceRecordViewSet,
    LeaveApplicationViewSet,
    EmployeeProfileAPIView
)
from erp_crm.tracking_views import CheckInAPIView, CheckOutAPIView, TodayAttendanceAPIView

router = DefaultRouter()
router.register(r'employees', EmployeeViewSet, basename='employee')
router.register(r'attendance', AttendanceRecordViewSet, basename='attendance')
router.register(r'leaves', LeaveApplicationViewSet, basename='leave')

urlpatterns = [
    # Dedicated Mobile App Employee Profile Endpoints
    path('profile/me/', EmployeeProfileAPIView.as_view(), name='employee-profile-me'),
    path('profile/update/', EmployeeProfileAPIView.as_view(), name='employee-profile-update'),
    
    # Check-In & Check-Out Endpoints for Mobile App
    path('check-in/', CheckInAPIView.as_view(), name='hr-check-in'),
    path('check-out/', CheckOutAPIView.as_view(), name='hr-check-out'),
    path('attendance/check-in/', CheckInAPIView.as_view(), name='hr-attendance-check-in'),
    path('attendance/check-out/', CheckOutAPIView.as_view(), name='hr-attendance-check-out'),
    path('attendance/today/', TodayAttendanceAPIView.as_view(), name='hr-attendance-today'),

    path('', include(router.urls)),
]
