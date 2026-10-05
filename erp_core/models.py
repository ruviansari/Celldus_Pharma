import uuid
from decimal import Decimal
from django.db import models, transaction
from django.conf import settings
from django.utils import timezone
from django.core.exceptions import ValidationError


class Branch(models.Model):
    """Manufacturing site, warehouse, or corporate branch."""
    SITE_TYPE_CHOICES = (
        ('manufacturing', 'Manufacturing Site'),
        ('warehouse', 'Central / Regional Warehouse'),
        ('office', 'Corporate / Sales Office'),
        ('rnd', 'R&D / QC Laboratory'),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=20, unique=True, help_text="e.g. SITE-01, WH-DELHI")
    name = models.CharField(max_length=150)
    site_type = models.CharField(max_length=30, choices=SITE_TYPE_CHOICES, default='manufacturing')
    address = models.TextField()
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=100)
    country = models.CharField(max_length=100, default='India')
    postal_code = models.CharField(max_length=20, blank=True)
    gstin = models.CharField(max_length=20, blank=True, help_text="Tax / GST Identification Number")
    drug_license_no = models.CharField(max_length=100, blank=True, help_text="Site Drug License Number")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = "Branches & Sites"
        ordering = ['code']

    def __str__(self):
        return f"[{self.code}] {self.name}"


class DocumentSequence(models.Model):
    """
    Server-generated sequential numbering per document type and financial year.
    Never recycled, strictly monotonic for compliance.
    """
    prefix = models.CharField(max_length=20)
    financial_year = models.CharField(max_length=10, help_text="e.g. 2026-27 or 2026")
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, null=True, blank=True)
    last_sequence = models.PositiveIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('prefix', 'financial_year', 'branch')

    @classmethod
    def get_next_number(cls, prefix: str, branch: Branch = None) -> str:
        """
        Atomically increments and returns the next document number,
        e.g., PR-2026-00001, PO-2026-00001, GRN-2026-00001.
        """
        now = timezone.now()
        # Indian Financial Year format (April to March) or Calendar Year
        if now.month >= 4:
            fy = f"{now.year}-{str(now.year + 1)[-2:]}"
        else:
            fy = f"{now.year - 1}-{str(now.year)[-2:]}"

        with transaction.atomic():
            seq_obj, created = cls.objects.select_for_update().get_or_create(
                prefix=prefix.upper(),
                financial_year=fy,
                branch=branch,
                defaults={'last_sequence': 0}
            )
            seq_obj.last_sequence += 1
            seq_obj.save(update_fields=['last_sequence', 'updated_at'])

            branch_tag = f"{branch.code}-" if branch else ""
            return f"{prefix.upper()}-{branch_tag}{fy}-{seq_obj.last_sequence:05d}"


class ERPBaseModel(models.Model):
    """
    Abstract base model providing:
    - Immutable UUID primary key
    - Full timestamps (UTC)
    - User attribution (created_by, updated_by)
    - Optimistic locking (version)
    - Soft-deactivation flag (no silent physical deletes)
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="%(app_label)s_%(class)s_created"
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="%(app_label)s_%(class)s_updated"
    )
    version = models.PositiveIntegerField(default=1, help_text="Optimistic locking version counter")
    is_active = models.BooleanField(default=True)

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        # Auto-increment version on update for optimistic locking
        if self.pk and not kwargs.get('force_insert', False):
            self.version += 1
        super().save(*args, **kwargs)


class ERPDocumentModel(ERPBaseModel):
    """
    Abstract model for regulated business transactions
    (Requisitions, Purchase Orders, GRNs, Production Orders, Invoices).
    """
    document_no = models.CharField(max_length=64, unique=True, editable=False, db_index=True)
    branch = models.ForeignKey(Branch, on_delete=models.PROTECT, null=True, blank=True)
    status = models.CharField(max_length=32, default='draft', db_index=True)
    remarks = models.TextField(blank=True)
    rejection_reason = models.TextField(blank=True, help_text="Required when rejecting a document")

    # Attributable Approval Metadata
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="%(app_label)s_%(class)s_approved"
    )
    approved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        abstract = True


class ERPUserRole(models.Model):
    """
    Celldus Pharma 10 Enterprise Roles matrix definition:
    1. Admin
    2. Purchase
    3. Warehouse
    4. Production
    5. QC Analyst
    6. QA Approver
    7. Sales/CRM
    8. Accounts
    9. HR/Payroll
    10. Auditor (Read-only)
    """
    ROLE_CHOICES = (
        ('ADMIN', 'System Administrator'),
        ('PURCHASE', 'Purchase Officer / Manager'),
        ('WAREHOUSE', 'Warehouse & Inventory Manager'),
        ('PRODUCTION', 'Production Officer / Planner'),
        ('QC_ANALYST', 'Quality Control (QC) Analyst'),
        ('QA_APPROVER', 'Quality Assurance (QA) Approver'),
        ('SALES_CRM', 'Sales & CRM Representative'),
        ('ACCOUNTS', 'Finance & Accounts Officer'),
        ('HR_PAYROLL', 'HR & Payroll Manager'),
        ('AUDITOR', 'Regulatory & Compliance Auditor (Read-Only)'),
    )

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='erp_roles')
    role = models.CharField(max_length=30, choices=ROLE_CHOICES)
    branch = models.ForeignKey(Branch, on_delete=models.SET_NULL, null=True, blank=True, help_text="Scope to branch or null for all")
    assigned_at = models.DateTimeField(auto_now_add=True)
    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assigned_roles'
    )

    class Meta:
        unique_together = ('user', 'role', 'branch')
        verbose_name = "User ERP Role"
        verbose_name_plural = "User ERP Roles"

    def __str__(self):
        return f"{self.user.username} -> {self.get_role_display()}"


class AuditLog(models.Model):
    """
    21 CFR Part 11 Compliant Audit Trail Log.
    Immutable, chronologically ordered, attributable record of every state transition,
    master modification, approval, rejection, and critical business event.
    """
    ACTION_CHOICES = (
        ('CREATE', 'Created Record'),
        ('UPDATE', 'Updated Record'),
        ('DELETE_ATTEMPT', 'Blocked Delete Attempt'),
        ('APPROVE', 'Authorized Approval'),
        ('REJECT', 'Rejected with Reason'),
        ('POST', 'Financial / Stock Ledger Posted'),
        ('DISPATCH', 'Material Dispatched'),
        ('QA_RELEASE', 'QA Batch Released'),
        ('QA_REJECT', 'QA Batch Rejected'),
        ('QA_HOLD', 'QA Quarantine / Hold Imposed'),
        ('RECALL', 'Product Batch Recalled'),
        ('LOGIN', 'User Login'),
        ('LOGOUT', 'User Logout'),
        ('SECURITY_ALERT', 'Security Exception / Violation'),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    timestamp = models.DateTimeField(default=timezone.now, db_index=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    action = models.CharField(max_length=30, choices=ACTION_CHOICES)
    entity_name = models.CharField(max_length=100, db_index=True)
    entity_id = models.CharField(max_length=100, db_index=True)
    document_no = models.CharField(max_length=100, blank=True, db_index=True)
    branch = models.ForeignKey(Branch, null=True, blank=True, on_delete=models.SET_NULL)
    reason = models.TextField(blank=True, help_text="Mandatory for overrides, corrections, rejections")
    changes = models.JSONField(default=dict, blank=True, help_text="Structured before/after diff")
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)

    class Meta:
        ordering = ['-timestamp']
        verbose_name = "Audit Trail Record"
        verbose_name_plural = "Audit Trail Records"

    def __str__(self):
        return f"[{self.timestamp.strftime('%Y-%m-%d %H:%M:%S')}] {self.user} - {self.action} on {self.entity_name} ({self.entity_id})"

    def save(self, *args, **kwargs):
        # Strict immutability: once saved, an audit record can never be modified
        if self.pk and AuditLog.objects.filter(pk=self.pk).exists():
            raise ValidationError("Audit log records are immutable and cannot be updated.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Audit log records can NEVER be deleted. Physical deletion is strictly prohibited by 21 CFR Part 11.")


class IdempotencyKey(models.Model):
    """
    Prevents duplicate submissions for retry-sensitive operations
    (bulk imports, payment postings, stock reservations).
    """
    key = models.CharField(max_length=255, unique=True, db_index=True)
    endpoint = models.CharField(max_length=255)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    response_code = models.IntegerField(null=True)
    response_body = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()

    def is_expired(self):
        return timezone.now() > self.expires_at

    def __str__(self):
        return f"{self.key} ({self.user.username})"
