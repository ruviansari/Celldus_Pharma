"""
URL Routing for Celldus Pharma Employee Tracking, SFA & Geofencing REST APIs.
"""
from django.urls import path
from .tracking_views import (
    # Attendance
    CheckInAPIView, CheckOutAPIView, TodayAttendanceAPIView,
    # Beat Plan
    TodayBeatPlanAPIView, BeatPlanDetailAPIView,
    # Visits
    FieldVisitListAPIView, FieldVisitDetailAPIView,
    FieldVisitStartAPIView, FieldVisitEndAPIView,
    # Tracking
    LiveTeamTrackingAPIView, EmployeeTimelineAPIView, OfflineBatchSyncAPIView,
    # Reports
    AttendanceReportAPIView, VisitsReportAPIView,
    PerformanceReportAPIView, ExceptionsReportAPIView
)

urlpatterns = [
    # Attendance
    path('attendance/check-in/', CheckInAPIView.as_view(), name='tracking_check_in'),
    path('attendance/check-out/', CheckOutAPIView.as_view(), name='tracking_check_out'),
    path('attendance/today/', TodayAttendanceAPIView.as_view(), name='tracking_attendance_today'),

    # Beat Plan
    path('beat-plan/today/', TodayBeatPlanAPIView.as_view(), name='tracking_beat_plan_today'),
    path('beat-plan/', BeatPlanDetailAPIView.as_view(), name='tracking_beat_plan_create'),
    path('beat-plan/<uuid:pk>/', BeatPlanDetailAPIView.as_view(), name='tracking_beat_plan_detail'),

    # Visits
    path('visits/', FieldVisitListAPIView.as_view(), name='tracking_visits_list'),
    path('visits/<uuid:pk>/', FieldVisitDetailAPIView.as_view(), name='tracking_visits_detail'),
    path('visits/start/', FieldVisitStartAPIView.as_view(), name='tracking_visits_start'),
    path('visits/<uuid:pk>/end/', FieldVisitEndAPIView.as_view(), name='tracking_visits_end'),

    # Tracking
    path('employees/current/', LiveTeamTrackingAPIView.as_view(), name='tracking_employees_current'),
    path('employees/<uuid:pk>/timeline/', EmployeeTimelineAPIView.as_view(), name='tracking_employee_timeline'),
    path('events/sync/', OfflineBatchSyncAPIView.as_view(), name='tracking_events_sync'),

    # Reports
    path('reports/attendance/', AttendanceReportAPIView.as_view(), name='tracking_reports_attendance'),
    path('reports/visits/', VisitsReportAPIView.as_view(), name='tracking_reports_visits'),
    path('reports/performance/', PerformanceReportAPIView.as_view(), name='tracking_reports_performance'),
    path('reports/exceptions/', ExceptionsReportAPIView.as_view(), name='tracking_reports_exceptions'),
]
