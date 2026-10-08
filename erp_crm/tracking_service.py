"""
Enterprise Field Force & Tracking Service Layer.
Executes business workflows for Attendance, Geofencing, Beat Plans, Visits, and GPS Logs.
"""
from decimal import Decimal
from typing import List, Dict, Any, Optional
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError, PermissionDenied, NotFound

from erp_core.security import audit_log_event
from erp_masters.models import CustomerMaster, ItemMaster
from erp_hr.models import Employee, AttendanceRecord
from .models import (
    DailyBeatPlan, FieldVisit, VisitProductDiscussed,
    VisitSampleGiven, VisitOrderBooking, EmployeeLocationEvent,
    FollowUpTask, Lead
)
from .geofence_service import validate_geofence, calculate_haversine_distance
from .tracking_config import (
    GPS_ACCURACY_WARN_THRESHOLD_METERS,
    MIN_VISIT_DURATION_MINUTES,
    MAX_IMPOSSIBLE_SPEED_KMH,
)


class TrackingService:

    @classmethod
    @transaction.atomic
    def process_check_in(
        cls,
        employee: Employee,
        lat: Any,
        lng: Any,
        accuracy: Optional[float] = None,
        address: str = '',
        work_mode: str = 'FIELD',
        battery: Optional[int] = None,
        is_mock: bool = False,
        idempotency_key: str = ''
    ) -> AttendanceRecord:
        """
        Processes duty check-in for the employee on today's date.
        Guarantees single daily record and strict server timestamps.
        """
        today = timezone.localdate()
        local_now = timezone.localtime()
        now_time = timezone.now()

        # Deduplication via idempotency key
        if idempotency_key and EmployeeLocationEvent.objects.filter(idempotency_key=idempotency_key).exists():
            record = AttendanceRecord.objects.filter(employee=employee, date=today).first()
            if record:
                return record

        # Lock record if exists to prevent race condition
        existing = AttendanceRecord.objects.select_for_update().filter(employee=employee, date=today).first()
        if existing and existing.check_in_time:
            raise ValidationError({
                'code': 'ALREADY_CHECKED_IN',
                'detail': f"You have already checked in for today ({today}) at {timezone.localtime(existing.check_in_time).strftime('%H:%M:%S')}."
            })

        acc = float(accuracy) if accuracy is not None else 0.0
        status_val = 'VALID'
        flag_reasons = []

        if is_mock:
            status_val = 'REQUIRES_REVIEW'
            flag_reasons.append("Mock GPS provider detected.")

        if acc > GPS_ACCURACY_WARN_THRESHOLD_METERS:
            status_val = 'POOR_ACCURACY'
            flag_reasons.append(f"Low accuracy GPS ({acc:.1f}m).")

        flag_str = "; ".join(flag_reasons)

        if not existing:
            attendance = AttendanceRecord.objects.create(
                employee=employee,
                date=today,
                in_time=local_now.time(),
                status='PRESENT',
                check_in_lat=Decimal(str(lat)) if lat is not None else None,
                check_in_lng=Decimal(str(lng)) if lng is not None else None,
                check_in_accuracy=acc,
                check_in_address=address or '',
                check_in_time=now_time,
                check_in_status=status_val,
                work_mode=work_mode,
                battery_level=battery,
                is_mock_location=is_mock,
                flag_reason=flag_str,
                created_by=employee.user,
                updated_by=employee.user,
            )
        else:
            existing.in_time = local_now.time()
            existing.status = 'PRESENT'
            existing.check_in_lat = Decimal(str(lat)) if lat is not None else None
            existing.check_in_lng = Decimal(str(lng)) if lng is not None else None
            existing.check_in_accuracy = acc
            existing.check_in_address = address or ''
            existing.check_in_time = now_time
            existing.check_in_status = status_val
            existing.work_mode = work_mode
            existing.battery_level = battery
            existing.is_mock_location = is_mock
            existing.flag_reason = flag_str
            existing.updated_by = employee.user
            existing.save()
            attendance = existing

        # Log immutable GPS event
        EmployeeLocationEvent.objects.create(
            employee=employee,
            event_type='CHECK_IN',
            server_timestamp=now_time,
            latitude=Decimal(str(lat or 0)),
            longitude=Decimal(str(lng or 0)),
            accuracy_meters=acc,
            battery_percentage=battery,
            is_mock=is_mock,
            geofence_status=status_val,
            is_flagged=bool(flag_reasons),
            flag_reason=flag_str,
            idempotency_key=idempotency_key or '',
            metadata={'work_mode': work_mode, 'address': address}
        )

        audit_log_event(
            user=employee.user,
            action='CHECK_IN',
            entity_name='AttendanceRecord',
            entity_id=attendance.id,
            reason=f"Field duty check-in at {now_time.strftime('%H:%M')} [{status_val}]"
        )
        return attendance

    @classmethod
    @transaction.atomic
    def process_check_out(
        cls,
        employee: Employee,
        lat: Any,
        lng: Any,
        accuracy: Optional[float] = None,
        address: str = '',
        idempotency_key: str = ''
    ) -> AttendanceRecord:
        """
        Processes duty check-out for the employee on today's date.
        """
        today = timezone.localdate()
        local_now = timezone.localtime()
        now_time = timezone.now()

        # Idempotency deduplication
        if idempotency_key and EmployeeLocationEvent.objects.filter(idempotency_key=idempotency_key).exists():
            record = AttendanceRecord.objects.filter(employee=employee, date=today).first()
            if record:
                return record

        attendance = AttendanceRecord.objects.select_for_update().filter(employee=employee, date=today).first()
        if not attendance or not attendance.check_in_time:
            raise ValidationError({
                'code': 'CHECK_IN_REQUIRED',
                'detail': "Cannot check out without an active check-in for today."
            })

        if attendance.check_out_time:
            raise ValidationError({
                'code': 'ALREADY_CHECKED_OUT',
                'detail': f"You have already checked out today at {timezone.localtime(attendance.check_out_time).strftime('%H:%M:%S')}."
            })

        # Ensure no active visits are left hanging in progress
        active_visit = FieldVisit.objects.filter(employee=employee, visit_status='IN_PROGRESS').first()
        if active_visit:
            raise ValidationError({
                'code': 'ACTIVE_VISIT_PENDING',
                'detail': f"Cannot check out: Visit #{active_visit.visit_no} at {active_visit.customer.name} is still in progress. Please complete or cancel it first."
            })

        acc = float(accuracy) if accuracy is not None else 0.0
        status_val = 'VALID'
        flag_reasons = []

        if acc > GPS_ACCURACY_WARN_THRESHOLD_METERS:
            status_val = 'POOR_ACCURACY'
            flag_reasons.append(f"Low accuracy GPS at checkout ({acc:.1f}m).")

        flag_str = "; ".join(flag_reasons)

        attendance.out_time = local_now.time()
        attendance.check_out_lat = Decimal(str(lat)) if lat is not None else None
        attendance.check_out_lng = Decimal(str(lng)) if lng is not None else None
        attendance.check_out_accuracy = acc
        attendance.check_out_address = address or ''
        attendance.check_out_time = now_time
        attendance.check_out_status = status_val
        if flag_str:
            attendance.flag_reason = (attendance.flag_reason + "; " + flag_str).strip("; ")
        attendance.updated_by = employee.user
        attendance.save()

        # Log location event
        EmployeeLocationEvent.objects.create(
            employee=employee,
            event_type='CHECK_OUT',
            server_timestamp=now_time,
            latitude=Decimal(str(lat or 0)),
            longitude=Decimal(str(lng or 0)),
            accuracy_meters=acc,
            is_mock=attendance.is_mock_location,
            geofence_status=status_val,
            is_flagged=bool(flag_reasons),
            flag_reason=flag_str,
            idempotency_key=idempotency_key or '',
            metadata={'address': address}
        )

        audit_log_event(
            user=employee.user,
            action='CHECK_OUT',
            entity_name='AttendanceRecord',
            entity_id=attendance.id,
            reason=f"Field duty check-out at {now_time.strftime('%H:%M')}"
        )
        return attendance

    @classmethod
    @transaction.atomic
    def start_field_visit(
        cls,
        employee: Employee,
        customer_id: str,
        lat: Any,
        lng: Any,
        accuracy: Optional[float] = None,
        beat_plan_id: Optional[str] = None,
        deviation_reason: str = '',
        idempotency_key: str = ''
    ) -> Dict[str, Any]:
        """
        Starts an in-person field detailing session with a doctor or chemist.
        Enforces geofence boundary checks and single active visit constraints.
        """
        today = timezone.now().date()
        now_time = timezone.now()

        # 1. Require check-in before visits
        att = AttendanceRecord.objects.filter(employee=employee, date=today, check_in_time__isnull=False).first()
        if not att:
            raise ValidationError({
                'code': 'CHECK_IN_REQUIRED',
                'detail': "You must check in for duty today before starting field visits."
            })

        # 2. Prevent concurrent active visits
        active_visit = FieldVisit.objects.filter(employee=employee, visit_status='IN_PROGRESS').first()
        if active_visit:
            raise ValidationError({
                'code': 'CONCURRENT_VISIT_PROHIBITED',
                'detail': f"Visit #{active_visit.visit_no} at {active_visit.customer.name} is currently in progress. Complete it before starting a new visit."
            })

        # 3. Retrieve target customer
        try:
            customer = CustomerMaster.objects.get(id=customer_id)
        except CustomerMaster.DoesNotExist:
            raise NotFound({"code": "CUSTOMER_NOT_FOUND", "detail": f"Customer ID {customer_id} not found."})

        # 4. Geofence evaluation
        geofence_res = validate_geofence(
            user_lat=lat,
            user_lng=lng,
            user_accuracy=accuracy,
            target_lat=customer.latitude,
            target_lng=customer.longitude,
            allowed_radius=customer.geofence_radius_meters
        )

        # Enforce deviation reason if out of range
        if geofence_res['validation_status'] == 'OUTSIDE_GEOFENCE' and not str(deviation_reason).strip():
            raise ValidationError({
                'code': 'GEOFENCE_DEVIATION_REQUIRED',
                'detail': f"You are {geofence_res['distance_meters']:.1f}m away from {customer.name} (outside {geofence_res['allowed_radius_meters']:.0f}m radius). A detailed deviation reason is mandatory to start this visit.",
                'data': geofence_res
            })

        beat_item = None
        if beat_plan_id:
            beat_item = DailyBeatPlan.objects.filter(id=beat_plan_id, employee=employee).first()

        visit = FieldVisit.objects.create(
            employee=employee,
            customer=customer,
            beat_plan=beat_item,
            branch=employee.branch,
            visit_date=today,
            visit_status='IN_PROGRESS',
            start_time=now_time,
            start_lat=Decimal(str(lat)) if lat is not None else None,
            start_lng=Decimal(str(lng)) if lng is not None else None,
            start_accuracy=float(accuracy) if accuracy is not None else None,
            distance_to_target_meters=geofence_res['distance_meters'],
            geofence_status=geofence_res['validation_status'],
            geofence_deviation_reason=deviation_reason or '',
            is_flagged=geofence_res['is_flagged'],
            flag_reason=geofence_res['flag_reason'],
            idempotency_key=idempotency_key or '',
            created_by=employee.user,
            updated_by=employee.user,
        )

        if beat_item:
            beat_item.status = 'IN_PROGRESS'
            beat_item.save(update_fields=['status'])

        # Log GPS event
        EmployeeLocationEvent.objects.create(
            employee=employee,
            event_type='VISIT_START',
            server_timestamp=now_time,
            latitude=Decimal(str(lat or 0)),
            longitude=Decimal(str(lng or 0)),
            accuracy_meters=float(accuracy or 0),
            distance_meters=geofence_res['distance_meters'],
            geofence_status=geofence_res['validation_status'],
            is_flagged=geofence_res['is_flagged'],
            flag_reason=geofence_res['flag_reason'],
            idempotency_key=idempotency_key or '',
            metadata={'visit_no': visit.visit_no, 'customer': customer.name}
        )

        audit_log_event(
            user=employee.user,
            action='VISIT_START',
            entity_name='FieldVisit',
            entity_id=visit.id,
            document_no=visit.visit_no,
            reason=f"Started detailing at {customer.name} (Dist: {geofence_res['distance_meters']:.1f}m)"
        )

        return {
            'visit': visit,
            'geofence_result': geofence_res
        }

    @classmethod
    @transaction.atomic
    def end_field_visit(
        cls,
        employee: Employee,
        visit_id: str,
        lat: Any,
        lng: Any,
        accuracy: Optional[float] = None,
        doctor_response: str = '',
        remarks: str = '',
        next_follow_up_date: Optional[str] = None,
        products_discussed: Optional[List[Dict[str, Any]]] = None,
        samples_given: Optional[List[Dict[str, Any]]] = None,
        booked_amount: Optional[Decimal] = None,
        idempotency_key: str = ''
    ) -> FieldVisit:
        """
        Completes an in-progress field visit, records detailing, samples, POB, and computes duration.
        """
        now_time = timezone.now()

        try:
            visit = FieldVisit.objects.select_for_update().get(id=visit_id)
        except FieldVisit.DoesNotExist:
            raise NotFound({"code": "VISIT_NOT_FOUND", "detail": f"Visit ID {visit_id} does not exist."})

        # Anti-IDOR: verify ownership
        if visit.employee_id != employee.id:
            raise PermissionDenied("You are not authorized to complete a visit assigned to another employee.")

        if visit.visit_status != 'IN_PROGRESS':
            raise ValidationError({
                'code': 'INVALID_VISIT_STATE',
                'detail': f"Visit is in '{visit.visit_status}' state and cannot be completed."
            })

        visit.end_time = now_time
        visit.end_lat = Decimal(str(lat)) if lat is not None else None
        visit.end_lng = Decimal(str(lng)) if lng is not None else None
        visit.end_accuracy = float(accuracy) if accuracy is not None else None

        # Compute duration
        duration_sec = (now_time - visit.start_time).total_seconds() if visit.start_time else 0
        duration_min = max(1, int(duration_sec // 60))
        visit.duration_minutes = duration_min

        # Flag very short visits (< threshold)
        if duration_min < MIN_VISIT_DURATION_MINUTES:
            visit.is_flagged = True
            reason = f"Unusually short visit ({duration_min} min < {MIN_VISIT_DURATION_MINUTES} min threshold)."
            visit.flag_reason = (visit.flag_reason + "; " + reason).strip("; ")

        visit.doctor_response = doctor_response or ''
        visit.remarks = remarks or ''
        visit.next_follow_up_date = next_follow_up_date or None
        visit.visit_status = 'COMPLETED'
        visit.updated_by = employee.user
        visit.save()

        # Update Beat Plan target if linked
        if visit.beat_plan:
            visit.beat_plan.status = 'COMPLETED'
            visit.beat_plan.save(update_fields=['status'])

        # Record products discussed
        if products_discussed:
            for item in products_discussed:
                prod_id = item.get('product_id')
                if prod_id:
                    prod = ItemMaster.objects.filter(id=prod_id, active_flag=True).first()
                    if prod:
                        VisitProductDiscussed.objects.create(
                            visit=visit,
                            product=prod,
                            is_core_focus=item.get('is_core_focus', True),
                            feedback=item.get('feedback', '')
                        )

        # Record samples given
        if samples_given:
            for item in samples_given:
                prod_id = item.get('product_id')
                qty = int(item.get('quantity', 1))
                if prod_id and qty > 0:
                    prod = ItemMaster.objects.filter(id=prod_id, active_flag=True).first()
                    if prod:
                        VisitSampleGiven.objects.create(
                            visit=visit,
                            product=prod,
                            quantity=qty,
                            batch_no=item.get('batch_no', '')
                        )

        # Record Order Booking (POB)
        if booked_amount and Decimal(str(booked_amount)) > Decimal('0.00'):
            VisitOrderBooking.objects.create(
                visit=visit,
                booked_amount=Decimal(str(booked_amount)),
                remarks=f"POB booked during visit #{visit.visit_no}"
            )

        # Automatically schedule CRM follow-up if next visit date specified
        if next_follow_up_date:
            lead = Lead.objects.filter(organization_name=visit.customer.name).first()
            if not lead:
                lead = Lead.objects.create(
                    organization_name=visit.customer.name,
                    contact_person=visit.customer.contact_person or 'Doctor / Chemist',
                    phone=visit.customer.phone or '0000000000',
                    city=visit.customer.city or 'Noida',
                    state=visit.customer.state or 'UP',
                    owner=employee.user,
                    stage='FOLLOW_UP'
                )
            FollowUpTask.objects.create(
                lead=lead,
                activity_type='VISIT',
                purpose=f"Next detailing follow-up: {remarks[:100]}",
                due_date=next_follow_up_date,
                assigned_to=employee.user,
                priority='MEDIUM',
                status='PENDING'
            )

        # Log GPS event
        EmployeeLocationEvent.objects.create(
            employee=employee,
            event_type='VISIT_END',
            server_timestamp=now_time,
            latitude=Decimal(str(lat or 0)),
            longitude=Decimal(str(lng or 0)),
            accuracy_meters=float(accuracy or 0),
            is_flagged=visit.is_flagged,
            flag_reason=visit.flag_reason,
            idempotency_key=idempotency_key or '',
            metadata={
                'visit_no': visit.visit_no,
                'duration_minutes': duration_min,
                'doctor_response': doctor_response,
                'pob_amount': float(booked_amount or 0.0)
            }
        )

        audit_log_event(
            user=employee.user,
            action='VISIT_END',
            entity_name='FieldVisit',
            entity_id=visit.id,
            document_no=visit.visit_no,
            reason=f"Completed visit in {duration_min}m (Resp: {doctor_response})"
        )

        return visit
