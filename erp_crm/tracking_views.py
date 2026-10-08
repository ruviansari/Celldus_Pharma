"""
REST API View Endpoints for Celldus Pharma Employee Tracking, SFA & Geofencing.
Enforces uniform response schemas, anti-IDOR boundaries, pagination, and robust error handling.
"""
from typing import Any, Optional, List, Dict
from decimal import Decimal
from django.db.models import Count, Sum, Avg, Q
from django.utils import timezone
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.pagination import PageNumberPagination
from rest_framework.exceptions import ValidationError, PermissionDenied, NotFound

from erp_masters.models import CustomerMaster
from erp_hr.models import Employee, AttendanceRecord
from .models import (
    DailyBeatPlan, FieldVisit, EmployeeLocationEvent,
    VisitOrderBooking, VisitSampleGiven, VisitProductDiscussed
)
from .tracking_permissions import (
    get_authenticated_employee,
    can_user_access_employee,
    is_sales_manager,
    is_system_or_hr_admin,
    get_subordinate_ids_recursive,
    IsFieldForceAuthenticated,
    IsManagerOrAdmin
)
from .tracking_serializers import (
    AttendancePunchSerializer,
    AttendanceRecordDetailSerializer,
    DailyBeatPlanSerializer,
    FieldVisitStartSerializer,
    FieldVisitEndSerializer,
    FieldVisitDetailSerializer,
    EmployeeLocationEventSerializer,
    OfflineBatchSyncSerializer
)
from .tracking_service import TrackingService


def api_response(
    success: bool,
    message: str,
    data: Any = None,
    error_code: str = None,
    status_code: int = status.HTTP_200_OK
) -> Response:
    """Consistent enterprise API response envelope."""
    payload = {
        "success": success,
        "message": message,
        "data": data if data is not None else {}
    }
    if not success and error_code:
        payload["error_code"] = error_code
    return Response(payload, status=status_code)


def format_serializer_errors(errors):
    if not errors:
        return "Validation failed."
    first_k = next(iter(errors))
    val = errors[first_k]
    if isinstance(val, (list, tuple)) and val:
        return f"{first_k}: {val[0]}"
    elif isinstance(val, dict):
        return format_serializer_errors(val)
    return f"{first_k}: {val}"


class StandardResultsSetPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100


# ==============================================================================
# 1. ATTENDANCE APIS (CHECK-IN, CHECK-OUT, TODAY STATUS)
# ==============================================================================

class CheckInAPIView(APIView):
    """
    POST /api/v1/tracking/attendance/check-in/
    Punches daily duty check-in with GPS coordinates & mock-location validation.
    """
    permission_classes = [IsAuthenticated, IsFieldForceAuthenticated]

    def post(self, request):
        employee = get_authenticated_employee(request.user)
        if not employee:
            return api_response(False, "No active employee profile linked.", "NO_EMPLOYEE_PROFILE", status_code=400)

        serializer = AttendancePunchSerializer(data=request.data)
        if not serializer.is_valid():
            return api_response(False, format_serializer_errors(serializer.errors), serializer.errors, "VALIDATION_ERROR", 400)

        data = serializer.validated_data
        try:
            record = TrackingService.process_check_in(
                employee=employee,
                lat=data['lat'],
                lng=data['lng'],
                accuracy=data.get('accuracy'),
                address=data.get('address', ''),
                work_mode=data.get('work_mode', 'FIELD'),
                battery=data.get('battery'),
                is_mock=data.get('is_mock', False),
                idempotency_key=data.get('idempotency_key', '')
            )
            out_serializer = AttendanceRecordDetailSerializer(record)
            return api_response(True, "Check-in successful.", out_serializer.data, status_code=200)
        except ValidationError as e:
            detail = e.detail if isinstance(e.detail, dict) else {'detail': str(e)}
            return api_response(False, detail.get('detail', str(e)), detail, detail.get('code', 'CHECK_IN_ERROR'), 400)
        except Exception as e:
            return api_response(False, str(e), error_code="SERVER_ERROR", status_code=500)


class CheckOutAPIView(APIView):
    """
    POST /api/v1/tracking/attendance/check-out/
    Punches daily duty check-out with GPS coordinates.
    """
    permission_classes = [IsAuthenticated, IsFieldForceAuthenticated]

    def post(self, request):
        employee = get_authenticated_employee(request.user)
        if not employee:
            return api_response(False, "No active employee profile linked.", "NO_EMPLOYEE_PROFILE", status_code=400)

        serializer = AttendancePunchSerializer(data=request.data)
        if not serializer.is_valid():
            return api_response(False, format_serializer_errors(serializer.errors), serializer.errors, "VALIDATION_ERROR", 400)

        data = serializer.validated_data
        try:
            record = TrackingService.process_check_out(
                employee=employee,
                lat=data['lat'],
                lng=data['lng'],
                accuracy=data.get('accuracy'),
                address=data.get('address', ''),
                idempotency_key=data.get('idempotency_key', '')
            )
            out_serializer = AttendanceRecordDetailSerializer(record)
            return api_response(True, "Check-out successful.", out_serializer.data, status_code=200)
        except ValidationError as e:
            detail = e.detail if isinstance(e.detail, dict) else {'detail': str(e)}
            return api_response(False, detail.get('detail', str(e)), detail, detail.get('code', 'CHECK_OUT_ERROR'), 400)
        except Exception as e:
            return api_response(False, str(e), error_code="SERVER_ERROR", status_code=500)


class TodayAttendanceAPIView(APIView):
    """
    GET /api/v1/tracking/attendance/today/
    Returns current check-in & check-out status of authenticated employee.
    """
    permission_classes = [IsAuthenticated, IsFieldForceAuthenticated]

    def get(self, request):
        employee = get_authenticated_employee(request.user)
        if not employee:
            return api_response(False, "No active employee profile linked.", "NO_EMPLOYEE_PROFILE", status_code=400)

        today = timezone.localdate()
        record = AttendanceRecord.objects.filter(employee=employee, date=today).first()
        if not record:
            return api_response(True, "Not checked in today.", {
                'is_checked_in': False,
                'is_checked_out': False,
                'has_checked_in': False,
                'has_checked_out': False,
                'check_in_time': None,
                'check_out_time': None,
                'record': None
            })

        check_in_str = None
        if record.check_in_time:
            check_in_str = timezone.localtime(record.check_in_time).strftime('%H:%M:%S')
        elif record.in_time:
            check_in_str = str(record.in_time)[:8]

        check_out_str = None
        if record.check_out_time:
            check_out_str = timezone.localtime(record.check_out_time).strftime('%H:%M:%S')
        elif record.out_time:
            check_out_str = str(record.out_time)[:8]

        return api_response(True, "Attendance retrieved.", {
            'is_checked_in': bool(record.check_in_time or record.in_time),
            'is_checked_out': bool(record.check_out_time or record.out_time),
            'has_checked_in': bool(record.check_in_time or record.in_time),
            'has_checked_out': bool(record.check_out_time or record.out_time),
            'check_in_time': check_in_str,
            'check_out_time': check_out_str,
            'check_in_lat': str(record.check_in_lat) if record.check_in_lat else None,
            'check_in_lng': str(record.check_in_lng) if record.check_in_lng else None,
            'record': AttendanceRecordDetailSerializer(record).data
        })


# ==============================================================================
# 2. BEAT PLAN APIS (TODAY, DETAIL, LIST)
# ==============================================================================

class TodayBeatPlanAPIView(APIView):
    """
    GET /api/v1/tracking/beat-plan/today/
    Returns scheduled doctors/chemists route targets for today.
    """
    permission_classes = [IsAuthenticated, IsFieldForceAuthenticated]

    def get(self, request):
        employee = get_authenticated_employee(request.user)
        target_emp_id = request.query_params.get('employee_id')

        # Manager override check
        if target_emp_id:
            try:
                target_emp = Employee.objects.get(id=target_emp_id)
                if not can_user_access_employee(request.user, target_emp):
                    raise PermissionDenied("You are not authorized to view beat plans for this employee.")
                employee = target_emp
            except Employee.DoesNotExist:
                return api_response(False, "Employee not found.", error_code="NOT_FOUND", status_code=404)

        if not employee:
            return api_response(False, "No active employee profile linked.", "NO_EMPLOYEE_PROFILE", status_code=400)

        date_str = request.query_params.get('date')
        plan_date = timezone.datetime.strptime(date_str, '%Y-%m-%d').date() if date_str else timezone.now().date()

        beat_items = DailyBeatPlan.objects.select_related('customer').filter(
            employee=employee,
            date=plan_date
        ).order_by('sequence')

        serializer = DailyBeatPlanSerializer(beat_items, many=True)
        return api_response(True, f"Beat plan for {plan_date}.", {
            'date': plan_date,
            'total_targets': beat_items.count(),
            'targets': serializer.data
        })


class BeatPlanDetailAPIView(APIView):
    """
    GET /api/v1/tracking/beat-plan/<id>/
    POST /api/v1/tracking/beat-plan/ (Assign target to beat)
    """
    permission_classes = [IsAuthenticated, IsFieldForceAuthenticated]

    def get(self, request, pk):
        try:
            item = DailyBeatPlan.objects.select_related('customer', 'employee').get(id=pk)
        except DailyBeatPlan.DoesNotExist:
            return api_response(False, "Beat item not found.", error_code="NOT_FOUND", status_code=404)

        if not can_user_access_employee(request.user, item.employee):
            raise PermissionDenied("Access to this beat plan item is forbidden.")

        serializer = DailyBeatPlanSerializer(item)
        return api_response(True, "Beat item retrieved.", serializer.data)

    def post(self, request):
        """Allows MR or Manager to add an ad-hoc target to today's beat."""
        employee = get_authenticated_employee(request.user)
        target_emp_id = request.data.get('employee_id')

        if target_emp_id and is_sales_manager(request.user):
            employee = Employee.objects.filter(id=target_emp_id).first() or employee

        if not employee:
            return api_response(False, "No active employee profile linked.", "NO_EMPLOYEE_PROFILE", status_code=400)

        serializer = DailyBeatPlanSerializer(data=request.data)
        if not serializer.is_valid():
            return api_response(False, "Validation failed.", serializer.errors, "VALIDATION_ERROR", 400)

        plan_date = serializer.validated_data.get('date', timezone.now().date())
        customer = serializer.validated_data['customer']

        # Determine sequence
        max_seq = DailyBeatPlan.objects.filter(employee=employee, date=plan_date).count() + 1

        beat_item = DailyBeatPlan.objects.create(
            employee=employee,
            customer=customer,
            date=plan_date,
            sequence=serializer.validated_data.get('sequence', max_seq),
            planned_time=serializer.validated_data.get('planned_time'),
            priority=serializer.validated_data.get('priority', 'MEDIUM'),
            notes=serializer.validated_data.get('notes', ''),
            created_by=request.user
        )

        return api_response(True, "Target added to beat plan.", DailyBeatPlanSerializer(beat_item).data, status_code=201)


# ==============================================================================
# 3. FIELD VISITS APIS (START, END, LIST, DETAIL)
# ==============================================================================

class FieldVisitStartAPIView(APIView):
    """
    POST /api/v1/tracking/visits/start/
    Initiates an in-person doctor/chemist visit detailing session.
    Calculates server-side distance and verifies geofencing.
    """
    permission_classes = [IsAuthenticated, IsFieldForceAuthenticated]

    def post(self, request):
        employee = get_authenticated_employee(request.user)
        if not employee:
            return api_response(False, "No active employee profile linked.", "NO_EMPLOYEE_PROFILE", status_code=400)

        serializer = FieldVisitStartSerializer(data=request.data)
        if not serializer.is_valid():
            return api_response(False, format_serializer_errors(serializer.errors), serializer.errors, "VALIDATION_ERROR", 400)

        data = serializer.validated_data
        try:
            res = TrackingService.start_field_visit(
                employee=employee,
                customer_id=str(data['customer_id']),
                lat=data['lat'],
                lng=data['lng'],
                accuracy=data.get('accuracy'),
                beat_plan_id=str(data['beat_plan_id']) if data.get('beat_plan_id') else None,
                deviation_reason=data.get('deviation_reason', ''),
                idempotency_key=data.get('idempotency_key', '')
            )
            out = FieldVisitDetailSerializer(res['visit']).data
            out['geofence_result'] = res['geofence_result']
            return api_response(True, f"Visit #{res['visit'].visit_no} started.", out, status_code=200)
        except ValidationError as e:
            detail = e.detail if isinstance(e.detail, dict) else {'detail': str(e)}
            return api_response(False, detail.get('detail', str(e)), detail, detail.get('code', 'VISIT_START_ERROR'), 400)
        except Exception as e:
            return api_response(False, str(e), error_code="SERVER_ERROR", status_code=500)


class FieldVisitEndAPIView(APIView):
    """
    POST /api/v1/tracking/visits/<id>/end/
    Completes detailing session, records feedback, sample delivery, and POB.
    """
    permission_classes = [IsAuthenticated, IsFieldForceAuthenticated]

    def post(self, request, pk):
        employee = get_authenticated_employee(request.user)
        if not employee:
            return api_response(False, "No active employee profile linked.", "NO_EMPLOYEE_PROFILE", status_code=400)

        serializer = FieldVisitEndSerializer(data=request.data)
        if not serializer.is_valid():
            return api_response(False, format_serializer_errors(serializer.errors), serializer.errors, "VALIDATION_ERROR", 400)

        data = serializer.validated_data
        try:
            visit = TrackingService.end_field_visit(
                employee=employee,
                visit_id=str(pk),
                lat=data['lat'],
                lng=data['lng'],
                accuracy=data.get('accuracy'),
                doctor_response=data.get('doctor_response', ''),
                remarks=data.get('remarks', ''),
                next_follow_up_date=data.get('next_follow_up_date'),
                products_discussed=data.get('products_discussed'),
                samples_given=data.get('samples_given'),
                booked_amount=data.get('booked_amount'),
                idempotency_key=data.get('idempotency_key', '')
            )
            return api_response(True, f"Visit #{visit.visit_no} completed successfully.", FieldVisitDetailSerializer(visit).data)
        except PermissionDenied as e:
            msg = str(e.detail) if hasattr(e, 'detail') else str(e)
            return api_response(False, msg, error_code="PERMISSION_DENIED", status_code=403)
        except NotFound as e:
            detail = e.detail if isinstance(e.detail, dict) else {'detail': str(e)}
            return api_response(False, detail.get('detail', str(e)), detail, detail.get('code', 'NOT_FOUND'), status_code=404)
        except ValidationError as e:
            detail = e.detail if isinstance(e.detail, dict) else {'detail': str(e)}
            return api_response(False, detail.get('detail', str(e)), detail, detail.get('code', 'VISIT_END_ERROR'), status_code=400)
        except Exception as e:
            return api_response(False, str(e), error_code="SERVER_ERROR", status_code=500)


class FieldVisitListAPIView(APIView):
    """
    GET /api/v1/tracking/visits/
    Lists field visits with pagination, date filtering, and anti-IDOR role scoping.
    """
    permission_classes = [IsAuthenticated, IsFieldForceAuthenticated]

    def get(self, request):
        employee = get_authenticated_employee(request.user)
        visits_qs = FieldVisit.objects.select_related(
            'customer', 'employee', 'beat_plan'
        ).prefetch_related('products_discussed__product', 'samples_given__product', 'orders_booked').order_by('-start_time')

        # Anti-IDOR: Scope query based on role
        if not is_system_or_hr_admin(request.user):
            if is_sales_manager(request.user):
                subordinate_ids = get_subordinate_ids_recursive(employee)
                visits_qs = visits_qs.filter(Q(employee=employee) | Q(employee_id__in=subordinate_ids))
            else:
                visits_qs = visits_qs.filter(employee=employee)

        # Filters
        date_param = request.query_params.get('date')
        if date_param:
            visits_qs = visits_qs.filter(visit_date=date_param)

        status_param = request.query_params.get('status')
        if status_param:
            visits_qs = visits_qs.filter(visit_status=status_param)

        customer_param = request.query_params.get('customer_id')
        if customer_param:
            visits_qs = visits_qs.filter(customer_id=customer_param)

        emp_filter = request.query_params.get('employee_id')
        if emp_filter and (is_sales_manager(request.user) or is_system_or_hr_admin(request.user)):
            visits_qs = visits_qs.filter(employee_id=emp_filter)

        paginator = StandardResultsSetPagination()
        page = paginator.paginate_queryset(visits_qs, request)
        serializer = FieldVisitDetailSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)


class FieldVisitDetailAPIView(APIView):
    """
    GET /api/v1/tracking/visits/<id>/
    Retrieves full detailing and GPS outcome of a single field visit.
    """
    permission_classes = [IsAuthenticated, IsFieldForceAuthenticated]

    def get(self, request, pk):
        try:
            visit = FieldVisit.objects.select_related('customer', 'employee').get(id=pk)
        except FieldVisit.DoesNotExist:
            return api_response(False, "Visit not found.", error_code="NOT_FOUND", status_code=404)

        if not can_user_access_employee(request.user, visit.employee):
            raise PermissionDenied("You are not authorized to view this visit.")

        serializer = FieldVisitDetailSerializer(visit)
        return api_response(True, "Visit retrieved.", serializer.data)


# ==============================================================================
# 4. LIVE TRACKING & TIMELINE APIS
# ==============================================================================

class LiveTeamTrackingAPIView(APIView):
    """
    GET /api/v1/tracking/employees/current/
    Manager / Admin Cockpit: Real-time status, active check-in, and location of sales team.
    """
    permission_classes = [IsAuthenticated, IsManagerOrAdmin]

    def get(self, request):
        current_emp = get_authenticated_employee(request.user)
        today = timezone.now().date()

        if is_system_or_hr_admin(request.user):
            employees_qs = Employee.objects.filter(is_active=True, department='SALES')
        else:
            sub_ids = get_subordinate_ids_recursive(current_emp)
            employees_qs = Employee.objects.filter(id__in=sub_ids, is_active=True)

        team_status = []
        for emp in employees_qs.select_related('territory'):
            # Latest attendance
            att = AttendanceRecord.objects.filter(employee=emp, date=today).first()
            # Latest location event
            last_event = EmployeeLocationEvent.objects.filter(employee=emp).order_by('-server_timestamp').first()
            # Active visit
            active_visit = FieldVisit.objects.select_related('customer').filter(employee=emp, visit_status='IN_PROGRESS').first()
            # Completed visits count
            completed_visits = FieldVisit.objects.filter(employee=emp, visit_date=today, visit_status='COMPLETED').count()

            # Location fallback: last_event -> att.check_in
            loc_data = None
            if last_event and last_event.latitude and last_event.longitude:
                loc_data = {
                    'lat': float(last_event.latitude),
                    'lng': float(last_event.longitude),
                    'latitude': float(last_event.latitude),
                    'longitude': float(last_event.longitude),
                    'accuracy': last_event.accuracy_meters,
                    'timestamp': last_event.server_timestamp.isoformat() if last_event.server_timestamp else None,
                    'event_type': last_event.event_type
                }
            elif att and att.check_in_lat and att.check_in_lng:
                loc_data = {
                    'lat': float(att.check_in_lat),
                    'lng': float(att.check_in_lng),
                    'latitude': float(att.check_in_lat),
                    'longitude': float(att.check_in_lng),
                    'accuracy': att.check_in_accuracy or 10.0,
                    'timestamp': att.check_in_time.isoformat() if att.check_in_time else None,
                    'event_type': 'CHECK_IN'
                }

            att_status = att.check_in_status if att else 'NOT_CHECKED_IN'
            if att and not att.check_in_time:
                att_status = 'NOT_CHECKED_IN'

            team_status.append({
                'employee_id': str(emp.id),
                'employee_code': emp.employee_code,
                'name': f"{emp.first_name} {emp.last_name}",
                'first_name': emp.first_name,
                'last_name': emp.last_name,
                'designation': emp.designation,
                'sales_tier': emp.sales_tier,
                'territory': emp.territory.name if emp.territory else 'Unassigned',
                'is_checked_in': bool(att and (att.check_in_time or att.in_time)),
                'check_in_time': timezone.localtime(att.check_in_time).strftime('%H:%M') if att and att.check_in_time else (str(att.in_time)[:5] if att and att.in_time else None),
                'is_checked_out': bool(att and (att.check_out_time or att.out_time)),
                'attendance_status': att_status,
                'is_active_in_visit': bool(active_visit),
                'last_known_location': loc_data,
                'current_activity': f"At {active_visit.customer.name}" if active_visit else ("On Duty" if (att and not att.check_out_time) else "Off Duty"),
                'visits_completed_today': completed_visits,
                'is_flagged': bool(att and att.flag_reason)
            })

        # Activity feed items for today
        feed_items = []
        for v in FieldVisit.objects.select_related('customer', 'employee').filter(visit_date=today).order_by('-start_time')[:15]:
            feed_items.append({
                'id': str(v.id),
                'type': 'VISIT',
                'title': f"{v.employee.first_name} {v.employee.last_name} @ {v.customer.name}",
                'subtitle': f"{v.customer.customer_type} | {v.customer.city or 'Field'}",
                'time': v.start_time.strftime('%H:%M') if v.start_time else '--:--',
                'status': v.visit_status,
                'is_flagged': v.is_flagged,
                'flag_reason': v.flag_reason,
                'employee_id': str(v.employee_id),
                'employee_name': f"{v.employee.first_name} {v.employee.last_name}",
                'lat': float(v.start_lat) if v.start_lat else None,
                'lng': float(v.start_lng) if v.start_lng else None
            })

        for a in AttendanceRecord.objects.select_related('employee').filter(date=today, check_in_time__isnull=False).order_by('-check_in_time')[:15]:
            feed_items.append({
                'id': str(a.id),
                'type': 'ATTENDANCE',
                'title': f"{a.employee.first_name} {a.employee.last_name} Punched In",
                'subtitle': f"Duty Mode: {a.work_mode} | {a.employee.territory.name if a.employee.territory else 'HQ'}",
                'time': timezone.localtime(a.check_in_time).strftime('%H:%M') if a.check_in_time else (str(a.in_time)[:5] if a.in_time else '--:--'),
                'status': a.check_in_status or 'PRESENT',
                'is_flagged': bool(a.flag_reason),
                'flag_reason': a.flag_reason,
                'employee_id': str(a.employee_id),
                'employee_name': f"{a.employee.first_name} {a.employee.last_name}",
                'lat': float(a.check_in_lat) if a.check_in_lat else None,
                'lng': float(a.check_in_lng) if a.check_in_lng else None
            })

        return api_response(True, "Live team status retrieved.", {
            'date': today,
            'total_subordinates': len(team_status),
            'active_on_field': sum(1 for e in team_status if e['is_checked_in'] and not e['is_checked_out']),
            'team': team_status,
            'employees': team_status,
            'activity_feed': feed_items
        })


class EmployeeTimelineAPIView(APIView):
    """
    GET /api/v1/tracking/employees/<id>/timeline/
    Returns chronological GPS events, check-ins, and visits for an employee on a given date.
    """
    permission_classes = [IsAuthenticated, IsFieldForceAuthenticated]

    def get(self, request, pk):
        try:
            target_emp = Employee.objects.get(id=pk)
        except Employee.DoesNotExist:
            return api_response(False, "Employee not found.", error_code="NOT_FOUND", status_code=404)

        if not can_user_access_employee(request.user, target_emp):
            raise PermissionDenied("Access to this employee's location timeline is forbidden.")

        date_str = request.query_params.get('date')
        target_date = timezone.datetime.strptime(date_str, '%Y-%m-%d').date() if date_str else timezone.now().date()

        # Query events within date range
        events = EmployeeLocationEvent.objects.filter(
            employee=target_emp,
            server_timestamp__date=target_date
        ).order_by('server_timestamp')

        serializer = EmployeeLocationEventSerializer(events, many=True)

        timeline_nodes = []
        for ev in events:
            timeline_nodes.append({
                'event': ev.event_type,
                'type': 'EVENT',
                'time': ev.server_timestamp.strftime('%H:%M:%S'),
                'geofence_status': ev.geofence_status,
                'is_flagged': ev.is_flagged,
                'flag_reason': ev.flag_reason,
                'battery': ev.battery_percentage,
                'customer': ev.metadata.get('customer_name', '') if isinstance(ev.metadata, dict) else '',
                'work_mode': ev.metadata.get('work_mode', '') if isinstance(ev.metadata, dict) else '',
                'lat': float(ev.latitude) if ev.latitude else None,
                'lng': float(ev.longitude) if ev.longitude else None
            })

        visits = FieldVisit.objects.select_related('customer').filter(employee=target_emp, visit_date=target_date).order_by('start_time')
        for v in visits:
            if v.start_time:
                timeline_nodes.append({
                    'event': 'VISIT_START',
                    'type': 'VISIT',
                    'time': v.start_time.strftime('%H:%M:%S'),
                    'geofence_status': v.geofence_status,
                    'is_flagged': v.is_flagged,
                    'flag_reason': v.flag_reason,
                    'customer': v.customer.name,
                    'lat': float(v.start_lat) if v.start_lat else None,
                    'lng': float(v.start_lng) if v.start_lng else None
                })
            if v.end_time:
                timeline_nodes.append({
                    'event': 'VISIT_END',
                    'type': 'VISIT',
                    'time': v.end_time.strftime('%H:%M:%S'),
                    'geofence_status': 'VALID',
                    'is_flagged': False,
                    'flag_reason': '',
                    'customer': v.customer.name,
                    'duration_minutes': v.duration_minutes,
                    'doctor_response': v.doctor_response,
                    'lat': float(v.end_lat) if v.end_lat else None,
                    'lng': float(v.end_lng) if v.end_lng else None
                })

        # Also include Attendance punch events if not already present in GPS events
        from erp_hr.models import AttendanceRecord
        att = AttendanceRecord.objects.filter(employee=target_emp, date=target_date).first()
        if att:
            has_checkin = any(n.get('event') == 'CHECK_IN' for n in timeline_nodes)
            if not has_checkin and att.check_in_time:
                timeline_nodes.append({
                    'event': 'CHECK_IN',
                    'type': 'EVENT',
                    'time': att.check_in_time.strftime('%H:%M:%S'),
                    'geofence_status': att.check_in_status or 'VALID',
                    'is_flagged': att.check_in_status in ['REQUIRES_REVIEW', 'OUTSIDE_GEOFENCE'],
                    'flag_reason': att.flag_reason or '',
                    'battery': att.battery_level,
                    'customer': '',
                    'work_mode': att.work_mode or 'FIELD',
                    'lat': float(att.check_in_lat) if att.check_in_lat else None,
                    'lng': float(att.check_in_lng) if att.check_in_lng else None
                })
            has_checkout = any(n.get('event') == 'CHECK_OUT' for n in timeline_nodes)
            if not has_checkout and att.check_out_time:
                timeline_nodes.append({
                    'event': 'CHECK_OUT',
                    'type': 'EVENT',
                    'time': att.check_out_time.strftime('%H:%M:%S'),
                    'geofence_status': 'VALID',
                    'is_flagged': False,
                    'flag_reason': '',
                    'battery': None,
                    'customer': '',
                    'work_mode': att.work_mode or 'FIELD',
                    'lat': float(att.check_out_lat) if att.check_out_lat else None,
                    'lng': float(att.check_out_lng) if att.check_out_lng else None
                })

        timeline_nodes.sort(key=lambda x: x.get('time', ''))

        return api_response(True, f"Timeline for {target_emp.first_name} on {target_date}.", {
            'employee_code': target_emp.employee_code,
            'employee_name': f"{target_emp.first_name} {target_emp.last_name}",
            'date': target_date,
            'event_count': len(timeline_nodes),
            'timeline': timeline_nodes,
            'events': serializer.data
        })


class OfflineBatchSyncAPIView(APIView):
    """
    POST /api/v1/tracking/events/sync/
    Idempotent batch upload of offline queued location events.
    """
    permission_classes = [IsAuthenticated, IsFieldForceAuthenticated]

    def post(self, request):
        employee = get_authenticated_employee(request.user)
        if not employee:
            return api_response(False, "No active employee profile linked.", "NO_EMPLOYEE_PROFILE", status_code=400)

        serializer = OfflineBatchSyncSerializer(data=request.data)
        if not serializer.is_valid():
            return api_response(False, "Validation failed.", serializer.errors, "VALIDATION_ERROR", 400)

        events_data = serializer.validated_data['events']
        synced_count = 0
        skipped_count = 0

        for item in events_data:
            key = item['idempotency_key']
            if EmployeeLocationEvent.objects.filter(idempotency_key=key).exists():
                skipped_count += 1
                continue

            EmployeeLocationEvent.objects.create(
                employee=employee,
                event_type=item['event_type'],
                server_timestamp=timezone.now(),
                device_timestamp=item.get('device_timestamp'),
                latitude=Decimal(str(item['lat'])),
                longitude=Decimal(str(item['lng'])),
                accuracy_meters=item.get('accuracy', 10.0),
                battery_percentage=item.get('battery'),
                is_mock=item.get('is_mock', False),
                idempotency_key=key,
                metadata=item.get('metadata', {})
            )
            synced_count += 1

        return api_response(True, f"Batch sync completed: {synced_count} inserted, {skipped_count} deduplicated.", {
            'synced': synced_count,
            'skipped': skipped_count
        })


# ==============================================================================
# 5. COMPREHENSIVE SFA REPORTS APIS
# ==============================================================================

class AttendanceReportAPIView(APIView):
    """
    GET /api/v1/tracking/reports/attendance/
    Aggregated attendance, work modes, and punctuality report.
    """
    permission_classes = [IsAuthenticated, IsManagerOrAdmin]

    def get(self, request):
        start_date = request.query_params.get('start_date', str(timezone.now().date()))
        end_date = request.query_params.get('end_date', str(timezone.now().date()))

        records = AttendanceRecord.objects.select_related('employee').filter(
            date__range=[start_date, end_date]
        )

        current_emp = get_authenticated_employee(request.user)
        if not is_system_or_hr_admin(request.user):
            sub_ids = get_subordinate_ids_recursive(current_emp)
            records = records.filter(Q(employee=current_emp) | Q(employee_id__in=sub_ids))

        summary = {
            'total_punches': records.count(),
            'present_count': records.filter(status='PRESENT').count(),
            'field_duty_count': records.filter(work_mode='FIELD').count(),
            'office_duty_count': records.filter(work_mode='OFFICE').count(),
            'flagged_punches': records.exclude(flag_reason='').count(),
        }

        serializer = AttendanceRecordDetailSerializer(records[:100], many=True)
        return api_response(True, "Attendance report generated.", {
            'summary': summary,
            'records': serializer.data
        })


class VisitsReportAPIView(APIView):
    """
    GET /api/v1/tracking/reports/visits/
    Aggregated field visit coverage, detailing stats, and doctor response breakdown.
    """
    permission_classes = [IsAuthenticated, IsManagerOrAdmin]

    def get(self, request):
        start_date = request.query_params.get('start_date', str(timezone.now().date()))
        end_date = request.query_params.get('end_date', str(timezone.now().date()))

        visits = FieldVisit.objects.filter(visit_date__range=[start_date, end_date])
        current_emp = get_authenticated_employee(request.user)

        if not is_system_or_hr_admin(request.user):
            sub_ids = get_subordinate_ids_recursive(current_emp)
            visits = visits.filter(Q(employee=current_emp) | Q(employee_id__in=sub_ids))

        total_visits = visits.count()
        completed = visits.filter(visit_status='COMPLETED')

        # Feedback breakdown
        feedback_breakdown = completed.values('doctor_response').annotate(count=Count('id'))
        geofence_breakdown = visits.values('geofence_status').annotate(count=Count('id'))
        total_pob = VisitOrderBooking.objects.filter(visit__in=completed).aggregate(total=Sum('booked_amount'))['total'] or Decimal('0.00')

        return api_response(True, "Visits report generated.", {
            'start_date': start_date,
            'end_date': end_date,
            'summary': {
                'total_scheduled': total_visits,
                'completed': completed.count(),
                'completion_rate_percent': round((completed.count() / total_visits * 100), 1) if total_visits > 0 else 0.0,
                'average_duration_minutes': round(completed.aggregate(avg=Avg('duration_minutes'))['avg'] or 0, 1),
                'total_pob_amount': float(total_pob),
            },
            'doctor_responses': feedback_breakdown,
            'geofence_compliance': geofence_breakdown
        })


class PerformanceReportAPIView(APIView):
    """
    GET /api/v1/tracking/reports/performance/
    Field Force Scorecard: Individual MR metrics (Visits, POB, Geofence %, Short Visits).
    """
    permission_classes = [IsAuthenticated, IsManagerOrAdmin]

    def get(self, request):
        today = timezone.now().date()
        start_date = request.query_params.get('start_date', str(today))
        end_date = request.query_params.get('end_date', str(today))

        current_emp = get_authenticated_employee(request.user)
        if is_system_or_hr_admin(request.user):
            employees_qs = Employee.objects.filter(is_active=True, department='SALES')
        else:
            sub_ids = get_subordinate_ids_recursive(current_emp)
            employees_qs = Employee.objects.filter(id__in=sub_ids, is_active=True)

        scorecards = []
        for emp in employees_qs.select_related('territory'):
            emp_visits = FieldVisit.objects.filter(employee=emp, visit_date__range=[start_date, end_date])
            total_v = emp_visits.count()
            completed_v = emp_visits.filter(visit_status='COMPLETED').count()
            verified_geofence = emp_visits.filter(geofence_status='VALID').count()
            flagged_v = emp_visits.filter(is_flagged=True).count()
            pob_sum = VisitOrderBooking.objects.filter(visit__in=emp_visits).aggregate(s=Sum('booked_amount'))['s'] or Decimal('0.00')

            scorecards.append({
                'employee_id': str(emp.id),
                'employee_code': emp.employee_code,
                'name': f"{emp.first_name} {emp.last_name}",
                'territory': emp.territory.name if emp.territory else 'General',
                'total_visits': total_v,
                'completed_visits': completed_v,
                'geofence_compliance_percent': round((verified_geofence / total_v * 100), 1) if total_v > 0 else 100.0,
                'flagged_exceptions_count': flagged_v,
                'pob_total_amount': float(pob_sum),
            })

        return api_response(True, "Performance scorecard generated.", {
            'start_date': start_date,
            'end_date': end_date,
            'scorecards': scorecards
        })


class ExceptionsReportAPIView(APIView):
    """
    GET /api/v1/tracking/reports/exceptions/
    Manager / Audit Report: Highlights outside geofence visits, mock GPS attempts, and short visits.
    """
    permission_classes = [IsAuthenticated, IsManagerOrAdmin]

    def get(self, request):
        today = timezone.now().date()
        start_date = request.query_params.get('start_date', str(today))
        end_date = request.query_params.get('end_date', str(today))

        flagged_visits = FieldVisit.objects.select_related('customer', 'employee').filter(
            visit_date__range=[start_date, end_date],
            is_flagged=True
        ).order_by('-start_time')

        current_emp = get_authenticated_employee(request.user)
        if not is_system_or_hr_admin(request.user):
            sub_ids = get_subordinate_ids_recursive(current_emp)
            flagged_visits = flagged_visits.filter(Q(employee=current_emp) | Q(employee_id__in=sub_ids))

        serializer = FieldVisitDetailSerializer(flagged_visits[:100], many=True)
        return api_response(True, "Exceptions audit report generated.", {
            'total_flagged_visits': flagged_visits.count(),
            'exceptions': serializer.data
        })
