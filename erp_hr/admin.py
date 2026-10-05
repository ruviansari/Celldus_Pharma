from django.contrib import admin
from .models import Employee, AttendanceRecord, LeaveApplication


@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = ('employee_code', 'first_name', 'last_name', 'department', 'designation', 'branch', 'is_active')
    list_filter = ('department', 'branch', 'is_active')
    search_fields = ('employee_code', 'first_name', 'last_name')


@admin.register(AttendanceRecord)
class AttendanceRecordAdmin(admin.ModelAdmin):
    list_display = ('employee', 'date', 'in_time', 'out_time', 'status', 'overtime_hours')
    list_filter = ('status', 'date')
    search_fields = ('employee__employee_code', 'employee__first_name')


@admin.register(LeaveApplication)
class LeaveApplicationAdmin(admin.ModelAdmin):
    list_display = ('document_no', 'employee', 'leave_type', 'from_date', 'to_date', 'days_count', 'status')
    list_filter = ('leave_type', 'status')
    search_fields = ('document_no', 'employee__first_name')
