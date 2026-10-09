"""
REST Framework Serializers for Attendance, Beat Plans, Field Visits, and GPS Tracking.
Provides strict validation, input sanitization, and structured nested output.
"""
from decimal import Decimal
from rest_framework import serializers
from erp_masters.models import CustomerMaster, ItemMaster, Territory
from erp_hr.models import Employee, AttendanceRecord
from .models import (
    DailyBeatPlan, FieldVisit, VisitProductDiscussed,
    VisitSampleGiven, VisitOrderBooking, EmployeeLocationEvent
)


# ==============================================================================
# ATTENDANCE SERIALIZERS
# ==============================================================================

class CoordinateField(serializers.Field):
    """
    Accepts float, int, str, Decimal with arbitrary precision,
    rounds to 6 decimal places, and converts to Decimal for accurate database storage.
    """
    def __init__(self, min_val=-90.0, max_val=90.0, **kwargs):
        self.min_val = min_val
        self.max_val = max_val
        super().__init__(**kwargs)

    def to_internal_value(self, data):
        if data is None:
            if self.required:
                raise serializers.ValidationError("This field is required.")
            return None
        try:
            val = float(data)
        except (ValueError, TypeError):
            raise serializers.ValidationError("A valid numeric coordinate is required.")
        if not (self.min_val <= val <= self.max_val):
            raise serializers.ValidationError(f"Coordinate must be between {self.min_val} and {self.max_val}.")
        return Decimal(f"{round(val, 6):.6f}")

    def to_representation(self, value):
        return str(value) if value is not None else None


class AttendancePunchSerializer(serializers.Serializer):
    """Payload for duty check-in & check-out."""
    lat = CoordinateField(min_val=-90.0, max_val=90.0, required=True)
    lng = CoordinateField(min_val=-180.0, max_val=180.0, required=True)
    accuracy = serializers.FloatField(required=False, default=10.0)
    address = serializers.CharField(max_length=255, required=False, allow_blank=True, default='')
    work_mode = serializers.ChoiceField(
        choices=['FIELD', 'HQ', 'OFFICE', 'TRANSIT'],
        default='FIELD',
        required=False
    )
    battery = serializers.IntegerField(min_value=0, max_value=100, required=False, allow_null=True)
    is_mock = serializers.BooleanField(default=False, required=False)
    idempotency_key = serializers.CharField(max_length=100, required=False, allow_blank=True, default='')

    def validate_work_mode(self, value):
        if value in ['HQ', 'OFFICE']:
            return 'OFFICE'
        return value


class AttendanceRecordDetailSerializer(serializers.ModelSerializer):
    employee_code = serializers.CharField(source='employee.employee_code', read_only=True)
    employee_name = serializers.SerializerMethodField()
    department = serializers.CharField(source='employee.department', read_only=True)
    designation = serializers.CharField(source='employee.designation', read_only=True)
    sales_tier = serializers.CharField(source='employee.sales_tier', read_only=True)

    class Meta:
        model = AttendanceRecord
        fields = [
            'id', 'employee', 'employee_code', 'employee_name', 'department',
            'designation', 'sales_tier', 'date', 'in_time', 'out_time',
            'status', 'work_mode', 'check_in_lat', 'check_in_lng',
            'check_in_accuracy', 'check_in_address', 'check_in_time', 'check_in_status',
            'check_out_lat', 'check_out_lng', 'check_out_accuracy',
            'check_out_address', 'check_out_time', 'check_out_status',
            'battery_level', 'is_mock_location', 'flag_reason'
        ]

    def get_employee_name(self, obj):
        return f"{obj.employee.first_name} {obj.employee.last_name}"


# ==============================================================================
# BEAT PLAN SERIALIZERS
# ==============================================================================

class CustomerBriefSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomerMaster
        fields = [
            'id', 'customer_code', 'name', 'customer_type',
            'billing_address', 'city', 'state', 'phone', 'contact_person',
            'latitude', 'longitude', 'geofence_radius_meters'
        ]


class DailyBeatPlanSerializer(serializers.ModelSerializer):
    customer = CustomerBriefSerializer(read_only=True)
    customer_id = serializers.PrimaryKeyRelatedField(
        queryset=CustomerMaster.objects.all(),
        source='customer'
    )
    employee_name = serializers.SerializerMethodField()

    class Meta:
        model = DailyBeatPlan
        fields = [
            'id', 'code', 'employee', 'employee_name', 'customer', 'customer_id',
            'date', 'sequence', 'planned_time', 'priority', 'status', 'notes'
        ]
        read_only_fields = ['code', 'employee']
        extra_kwargs = {
            'date': {'required': False}
        }

    def get_employee_name(self, obj):
        return f"{obj.employee.first_name} {obj.employee.last_name}"


# ==============================================================================
# FIELD VISIT SERIALIZERS
# ==============================================================================

class ProductDiscussedItemSerializer(serializers.Serializer):
    product_id = serializers.UUIDField(required=True)
    is_core_focus = serializers.BooleanField(default=True, required=False)
    feedback = serializers.CharField(max_length=255, required=False, allow_blank=True, default='')


class SampleGivenItemSerializer(serializers.Serializer):
    product_id = serializers.UUIDField(required=True)
    quantity = serializers.IntegerField(min_value=1, required=True)
    batch_no = serializers.CharField(max_length=50, required=False, allow_blank=True, default='')


class FieldVisitStartSerializer(serializers.Serializer):
    customer_id = serializers.UUIDField(required=True)
    lat = CoordinateField(min_val=-90.0, max_val=90.0, required=True)
    lng = CoordinateField(min_val=-180.0, max_val=180.0, required=True)
    accuracy = serializers.FloatField(required=False, default=10.0)
    beat_plan_id = serializers.UUIDField(required=False, allow_null=True)
    deviation_reason = serializers.CharField(required=False, allow_blank=True, default='')
    idempotency_key = serializers.CharField(max_length=100, required=False, allow_blank=True, default='')


class FieldVisitEndSerializer(serializers.Serializer):
    lat = CoordinateField(min_val=-90.0, max_val=90.0, required=True)
    lng = CoordinateField(min_val=-180.0, max_val=180.0, required=True)
    accuracy = serializers.FloatField(required=False, default=10.0)
    doctor_response = serializers.CharField(
        required=False,
        allow_blank=True,
        default='POSITIVE'
    )

    def validate_doctor_response(self, value):
        valid = {'HIGHLY_INTERESTED', 'POSITIVE', 'NEUTRAL', 'NOT_INTERESTED', 'BUSY'}
        if not value:
            return 'POSITIVE'
        val_upper = str(value).strip().upper()
        if val_upper in valid:
            return val_upper
        mapping = {
            '5': 'HIGHLY_INTERESTED',
            '4': 'POSITIVE',
            '3': 'NEUTRAL',
            '2': 'NOT_INTERESTED',
            '1': 'BUSY'
        }
        clean_val = str(value).strip()
        if clean_val in mapping:
            return mapping[clean_val]
        # Fallback to POSITIVE for free-form remarks or unexpected inputs
        return 'POSITIVE'
    remarks = serializers.CharField(required=False, allow_blank=True, default='')
    next_follow_up_date = serializers.DateField(required=False, allow_null=True)
    products_discussed = ProductDiscussedItemSerializer(many=True, required=False, default=[])
    samples_given = SampleGivenItemSerializer(many=True, required=False, default=[])
    booked_amount = serializers.DecimalField(max_digits=14, decimal_places=2, required=False, default=Decimal('0.00'))
    idempotency_key = serializers.CharField(max_length=100, required=False, allow_blank=True, default='')


class VisitProductDiscussedSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source='product.name', read_only=True)
    dosage_form = serializers.CharField(source='product.dosage_form', read_only=True)

    class Meta:
        model = VisitProductDiscussed
        fields = ['id', 'product', 'product_name', 'dosage_form', 'is_core_focus', 'feedback']


class VisitSampleGivenSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source='product.name', read_only=True)

    class Meta:
        model = VisitSampleGiven
        fields = ['id', 'product', 'product_name', 'quantity', 'batch_no']


class VisitOrderBookingSerializer(serializers.ModelSerializer):
    class Meta:
        model = VisitOrderBooking
        fields = ['id', 'order', 'booked_amount', 'remarks']


class FieldVisitDetailSerializer(serializers.ModelSerializer):
    customer = CustomerBriefSerializer(read_only=True)
    employee_name = serializers.SerializerMethodField()
    employee_code = serializers.CharField(source='employee.employee_code', read_only=True)
    products_discussed = VisitProductDiscussedSerializer(many=True, read_only=True)
    samples_given = VisitSampleGivenSerializer(many=True, read_only=True)
    orders_booked = VisitOrderBookingSerializer(many=True, read_only=True)

    class Meta:
        model = FieldVisit
        fields = [
            'id', 'visit_no', 'employee', 'employee_code', 'employee_name',
            'customer', 'beat_plan', 'visit_date', 'visit_status',
            'start_time', 'start_lat', 'start_lng', 'start_accuracy',
            'distance_to_target_meters', 'geofence_status', 'geofence_deviation_reason',
            'end_time', 'end_lat', 'end_lng', 'end_accuracy', 'duration_minutes',
            'doctor_response', 'next_follow_up_date', 'remarks',
            'is_flagged', 'flag_reason', 'products_discussed', 'samples_given', 'orders_booked'
        ]

    def get_employee_name(self, obj):
        return f"{obj.employee.first_name} {obj.employee.last_name}"


# ==============================================================================
# TRACKING & TIMELINE SERIALIZERS
# ==============================================================================

class EmployeeLocationEventSerializer(serializers.ModelSerializer):
    employee_name = serializers.SerializerMethodField()
    employee_code = serializers.CharField(source='employee.employee_code', read_only=True)

    class Meta:
        model = EmployeeLocationEvent
        fields = [
            'id', 'employee', 'employee_code', 'employee_name', 'event_type',
            'server_timestamp', 'device_timestamp', 'latitude', 'longitude',
            'accuracy_meters', 'battery_percentage', 'is_mock', 'distance_meters',
            'geofence_status', 'is_flagged', 'flag_reason', 'idempotency_key', 'metadata'
        ]

    def get_employee_name(self, obj):
        return f"{obj.employee.first_name} {obj.employee.last_name}"


class OfflineEventSyncItemSerializer(serializers.Serializer):
    idempotency_key = serializers.CharField(max_length=100, required=True)
    event_type = serializers.ChoiceField(
        choices=['CHECK_IN', 'CHECK_OUT', 'VISIT_START', 'VISIT_END', 'LOCATION_PING', 'OFFLINE_SYNC']
    )
    lat = CoordinateField(min_val=-90.0, max_val=90.0, required=True)
    lng = CoordinateField(min_val=-180.0, max_val=180.0, required=True)
    accuracy = serializers.FloatField(default=10.0)
    device_timestamp = serializers.DateTimeField(required=False)
    battery = serializers.IntegerField(required=False, allow_null=True)
    is_mock = serializers.BooleanField(default=False)
    metadata = serializers.DictField(required=False, default={})


class OfflineBatchSyncSerializer(serializers.Serializer):
    events = OfflineEventSyncItemSerializer(many=True, required=True)
