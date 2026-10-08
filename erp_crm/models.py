import uuid
from decimal import Decimal
from django.db import models
from django.conf import settings
from django.utils import timezone
from django.core.exceptions import ValidationError
from erp_core.models import ERPBaseModel, ERPDocumentModel, DocumentSequence


class Lead(ERPBaseModel):
    """
    Prospective pharmaceutical customer / distributor lead.
    """
    LEAD_TYPE_CHOICES = (
        ('DISTRIBUTOR', 'Distributor / Wholesaler'),
        ('STOCKIST', 'Stockist / C&F'),
        ('RETAILER', 'Retail Chemist / Pharmacy'),
        ('HOSPITAL', 'Hospital / Medical Center'),
        ('CLINIC', 'Doctor Clinic'),
        ('INSTITUTIONAL', 'Institutional / Government Buyer'),
        ('OTHER', 'Other'),
    )

    STAGE_CHOICES = (
        ('NEW', 'New Lead'),
        ('CONTACTED', 'Initial Contact Made'),
        ('FOLLOW_UP', 'Active Follow-Up'),
        ('QUALIFIED', 'Qualified Prospect'),
        ('QUOTATION', 'Quotation / Commercial Proposal Sent'),
        ('CONVERTED', 'Converted to Customer'),
        ('LOST', 'Lost Opportunity'),
    )

    lead_id = models.CharField(max_length=60, unique=True, editable=False, db_index=True)
    lead_type = models.CharField(max_length=30, choices=LEAD_TYPE_CHOICES, default='DISTRIBUTOR')
    organization_name = models.CharField(max_length=200, db_index=True)
    contact_person = models.CharField(max_length=150)
    phone = models.CharField(max_length=30, db_index=True)
    email = models.EmailField(blank=True, db_index=True)

    city = models.CharField(max_length=100)
    state = models.CharField(max_length=100)
    territory = models.CharField(max_length=100, blank=True)
    tax_or_drug_license = models.CharField(max_length=100, blank=True)

    source = models.CharField(max_length=100, default='Field Inquiry', help_text="e.g. Website, Medical Expo, Field Call")
    stage = models.CharField(max_length=30, choices=STAGE_CHOICES, default='NEW', db_index=True)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='assigned_leads')

    next_follow_up_date = models.DateField(null=True, blank=True, db_index=True)
    lost_reason = models.TextField(blank=True)
    notes = models.TextField(blank=True)

    def clean(self):
        super().clean()
        if self.stage == 'LOST' and not str(self.lost_reason).strip():
            raise ValidationError({
                'lost_reason': "A detailed lost reason is mandatory when marking a lead as LOST."
            })
        if self.phone:
            digits = ''.join(c for c in self.phone if c.isdigit())
            if len(digits) < 10:
                raise ValidationError({
                    'phone': "Contact phone number must have at least 10 digits."
                })

    def save(self, *args, **kwargs):
        self.clean()
        if not self.lead_id:
            self.lead_id = DocumentSequence.get_next_number('LEAD')
        super().save(*args, **kwargs)

    def __str__(self):
        return f"[{self.lead_id}] {self.organization_name} ({self.stage})"


class FollowUpTask(ERPBaseModel):
    """
    Scheduled CRM Follow-up activity.
    """
    ACTIVITY_CHOICES = (
        ('CALL', 'Phone Call'),
        ('VISIT', 'In-Person Detailing / Visit'),
        ('EMAIL', 'Email Follow-up / Quotation'),
        ('MEETING', 'Commercial Negotiation Meeting'),
    )

    STATUS_CHOICES = (
        ('PENDING', 'Pending / Scheduled'),
        ('COMPLETED', 'Completed'),
        ('RESCHEDULED', 'Rescheduled'),
        ('CANCELLED', 'Cancelled'),
    )

    lead = models.ForeignKey(Lead, on_delete=models.CASCADE, related_name='tasks')
    activity_type = models.CharField(max_length=20, choices=ACTIVITY_CHOICES, default='CALL')
    purpose = models.CharField(max_length=255)
    due_date = models.DateField(db_index=True)
    assigned_to = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='crm_tasks')
    priority = models.CharField(max_length=20, default='MEDIUM', choices=(('LOW', 'Low'), ('MEDIUM', 'Medium'), ('HIGH', 'High')))

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING', db_index=True)
    outcome_notes = models.TextField(blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.activity_type} with {self.lead.organization_name} (Due: {self.due_date}) [{self.status}]"


class LeadImportBatch(ERPBaseModel):
    """
    Tracks bulk Excel / CSV lead imports with validation summary.
    """
    batch_no = models.CharField(max_length=60, unique=True)
    file_name = models.CharField(max_length=255)
    total_rows = models.PositiveIntegerField(default=0)
    valid_rows = models.PositiveIntegerField(default=0)
    duplicate_rows = models.PositiveIntegerField(default=0)
    error_rows = models.PositiveIntegerField(default=0)
    import_summary = models.JSONField(default=dict)
    is_confirmed = models.BooleanField(default=False)

    def __str__(self):
        return f"Import {self.batch_no} ({self.valid_rows}/{self.total_rows} valid)"


# ==============================================================================
# FIELD FORCE SFA: BEAT PLANS, VISITS, DETAILING & EVENT-BASED GPS TRACKING
# ==============================================================================

class DailyBeatPlan(ERPBaseModel):
    """
    Daily route plan scheduled for a field sales representative or MR.
    """
    STATUS_CHOICES = (
        ('PLANNED', 'Planned'),
        ('IN_PROGRESS', 'In Progress'),
        ('COMPLETED', 'Completed'),
        ('MISSED', 'Missed'),
        ('CANCELLED', 'Cancelled'),
    )
    PRIORITY_CHOICES = (
        ('HIGH', 'High Priority'),
        ('MEDIUM', 'Medium Priority'),
        ('LOW', 'Low Priority'),
    )

    code = models.CharField(max_length=60, unique=True, editable=False, db_index=True)
    employee = models.ForeignKey('erp_hr.Employee', on_delete=models.PROTECT, related_name='beat_plans')
    customer = models.ForeignKey('erp_masters.CustomerMaster', on_delete=models.PROTECT, related_name='scheduled_beats')
    date = models.DateField(db_index=True)
    sequence = models.PositiveIntegerField(default=1)
    planned_time = models.TimeField(null=True, blank=True)
    priority = models.CharField(max_length=20, choices=PRIORITY_CHOICES, default='MEDIUM')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PLANNED', db_index=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['date', 'sequence']
        unique_together = ('employee', 'date', 'customer')

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = DocumentSequence.get_next_number('BEAT')
        super().save(*args, **kwargs)

    def __str__(self):
        return f"[{self.code}] {self.employee.first_name} -> {self.customer.name} on {self.date} (#{self.sequence})"


class FieldVisit(ERPDocumentModel):
    """
    In-person doctor/chemist visit detailing session executed by field representatives.
    Includes geofencing start & end verification.
    """
    STATUS_CHOICES = (
        ('PLANNED', 'Planned / Scheduled'),
        ('IN_PROGRESS', 'In Progress (Active Visit)'),
        ('COMPLETED', 'Completed & Submitted'),
        ('CANCELLED', 'Cancelled'),
    )
    GEOFENCE_STATUS_CHOICES = (
        ('VALID', 'Verified Inside Geofence'),
        ('OUTSIDE_GEOFENCE', 'Outside Target Geofence Boundary'),
        ('NO_COORDINATES', 'Target Has No Coordinates Set'),
        ('REQUIRES_REVIEW', 'Requires Manager Review (Poor GPS)'),
    )
    DOCTOR_RESPONSE_CHOICES = (
        ('HIGHLY_INTERESTED', 'Highly Interested / Prescribing Core Brands'),
        ('POSITIVE', 'Positive / Agreed to Trial Prescriptions'),
        ('NEUTRAL', 'Neutral / Existing Stocks Present'),
        ('NOT_INTERESTED', 'Not Interested Currently'),
        ('BUSY', 'Doctor / Chemist Busy, Requested Reschedule'),
    )

    visit_no = models.CharField(max_length=60, unique=True, editable=False, db_index=True)
    employee = models.ForeignKey('erp_hr.Employee', on_delete=models.PROTECT, related_name='field_visits')
    customer = models.ForeignKey('erp_masters.CustomerMaster', on_delete=models.PROTECT, related_name='field_visits')
    beat_plan = models.ForeignKey(DailyBeatPlan, null=True, blank=True, on_delete=models.SET_NULL, related_name='visits')
    visit_date = models.DateField(default=timezone.now, db_index=True)
    visit_status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PLANNED', db_index=True)

    # Start Coordinates & Geofencing
    start_time = models.DateTimeField(null=True, blank=True)
    start_lat = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    start_lng = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    start_accuracy = models.FloatField(null=True, blank=True)
    distance_to_target_meters = models.FloatField(null=True, blank=True)
    geofence_status = models.CharField(max_length=30, choices=GEOFENCE_STATUS_CHOICES, default='VALID', db_index=True)
    geofence_deviation_reason = models.TextField(blank=True, help_text="Mandatory justification when starting outside geofence boundary")

    # End Coordinates & Timing
    end_time = models.DateTimeField(null=True, blank=True)
    end_lat = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    end_lng = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    end_accuracy = models.FloatField(null=True, blank=True)
    duration_minutes = models.PositiveIntegerField(default=0)

    # Detailing Feedback & Commercials
    doctor_response = models.CharField(max_length=30, choices=DOCTOR_RESPONSE_CHOICES, blank=True)
    next_follow_up_date = models.DateField(null=True, blank=True)

    # Compliance Flagging & Deduplication
    is_flagged = models.BooleanField(default=False, db_index=True)
    flag_reason = models.CharField(max_length=255, blank=True)
    idempotency_key = models.CharField(max_length=100, blank=True, db_index=True)

    def save(self, *args, **kwargs):
        if not self.visit_no:
            self.visit_no = DocumentSequence.get_next_number('VISIT')
        if not self.document_no:
            self.document_no = self.visit_no
        super().save(*args, **kwargs)

    def __str__(self):
        return f"[{self.visit_no}] {self.employee.first_name} at {self.customer.name} ({self.visit_status})"


class VisitProductDiscussed(ERPBaseModel):
    """
    Pharma formulations & brand presentations detailed during a visit.
    """
    visit = models.ForeignKey(FieldVisit, on_delete=models.CASCADE, related_name='products_discussed')
    product = models.ForeignKey('erp_masters.ItemMaster', on_delete=models.PROTECT, limit_choices_to={'item_type': 'FINISHED_GOOD'})
    is_core_focus = models.BooleanField(default=True)
    feedback = models.CharField(max_length=255, blank=True)

    def __str__(self):
        return f"{self.visit.visit_no} -> {self.product.name}"


class VisitSampleGiven(ERPBaseModel):
    """
    Free samples, promotional literature, or doctor gifts distributed.
    """
    visit = models.ForeignKey(FieldVisit, on_delete=models.CASCADE, related_name='samples_given')
    product = models.ForeignKey('erp_masters.ItemMaster', on_delete=models.PROTECT, limit_choices_to={'item_type': 'FINISHED_GOOD'})
    quantity = models.PositiveIntegerField(default=1)
    batch_no = models.CharField(max_length=50, blank=True)

    def __str__(self):
        return f"{self.visit.visit_no}: {self.quantity} x {self.product.name} (Lot: {self.batch_no or 'N/A'})"


class VisitOrderBooking(ERPBaseModel):
    """
    Personal Order Booking (POB) booked directly with a chemist or stockist during visit.
    """
    visit = models.ForeignKey(FieldVisit, on_delete=models.CASCADE, related_name='orders_booked')
    order = models.ForeignKey('erp_sales.SalesOrder', null=True, blank=True, on_delete=models.SET_NULL, related_name='visit_bookings')
    booked_amount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'))
    remarks = models.TextField(blank=True)

    def __str__(self):
        return f"{self.visit.visit_no} booked POB ₹{self.booked_amount}"


class EmployeeLocationEvent(models.Model):
    """
    Immutable event-based GPS location audit trail.
    Tracks check-ins, check-outs, visit milestones, and offline sync.
    """
    EVENT_TYPES = (
        ('CHECK_IN', 'Daily Duty Check-In'),
        ('CHECK_OUT', 'Daily Duty Check-Out'),
        ('VISIT_START', 'Visit Started'),
        ('VISIT_END', 'Visit Finished'),
        ('LOCATION_PING', 'Periodic Verified Ping'),
        ('OFFLINE_SYNC', 'Offline Sync Event'),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    employee = models.ForeignKey('erp_hr.Employee', on_delete=models.CASCADE, related_name='location_events')
    event_type = models.CharField(max_length=20, choices=EVENT_TYPES, db_index=True)
    server_timestamp = models.DateTimeField(default=timezone.now, db_index=True)
    device_timestamp = models.DateTimeField(null=True, blank=True)

    latitude = models.DecimalField(max_digits=9, decimal_places=6)
    longitude = models.DecimalField(max_digits=9, decimal_places=6)
    accuracy_meters = models.FloatField()
    battery_percentage = models.PositiveSmallIntegerField(null=True, blank=True)
    is_mock = models.BooleanField(default=False)

    distance_meters = models.FloatField(null=True, blank=True)
    geofence_status = models.CharField(max_length=30, blank=True)
    is_flagged = models.BooleanField(default=False, db_index=True)
    flag_reason = models.CharField(max_length=255, blank=True)
    idempotency_key = models.CharField(max_length=100, blank=True, db_index=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ['-server_timestamp']
        indexes = [
            models.Index(fields=['employee', 'server_timestamp']),
            models.Index(fields=['event_type', 'server_timestamp']),
            models.Index(fields=['idempotency_key']),
        ]

    def __str__(self):
        return f"{self.employee.employee_code} - {self.event_type} at {self.server_timestamp.strftime('%Y-%m-%d %H:%M')}"
