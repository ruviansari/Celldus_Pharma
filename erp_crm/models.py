import uuid
from django.db import models
from django.conf import settings
from django.utils import timezone
from django.core.exceptions import ValidationError
from erp_core.models import ERPBaseModel, DocumentSequence


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
    assigned_to = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='crm_tasks')
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
