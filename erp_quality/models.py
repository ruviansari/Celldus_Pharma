import uuid
from decimal import Decimal
from django.db import models, transaction
from django.conf import settings
from django.utils import timezone
from django.core.exceptions import ValidationError
from erp_core.models import ERPBaseModel, ERPDocumentModel, DocumentSequence
from erp_inventory.models import InventoryLot, StockLedger
from erp_masters.models import ItemMaster, QualitySpecification, SpecificationParameter


class QCInspectionRequest(ERPDocumentModel):
    """
    Quality Control Inspection Request triggered automatically by GRN receipt or Batch Completion.
    """
    STATUS_CHOICES = (
        ('PENDING_SAMPLING', 'Pending Sample Collection'),
        ('SAMPLED', 'Sample Collected, Under Testing'),
        ('TESTING_COMPLETED', 'Testing Completed, Pending QA Review'),
        ('DISPOSITIONED', 'Quality Disposition Executed'),
    )

    lot = models.ForeignKey(InventoryLot, on_delete=models.PROTECT, related_name='qc_inspections')
    item = models.ForeignKey(ItemMaster, on_delete=models.PROTECT)
    specification = models.ForeignKey(QualitySpecification, on_delete=models.PROTECT)

    # Sampling details
    sample_quantity = models.DecimalField(max_digits=12, decimal_places=4, default=Decimal('0.0000'))
    sample_uom_code = models.CharField(max_length=20, default='GM')
    sampler = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='collected_samples')
    sampled_at = models.DateTimeField(null=True, blank=True)
    sampling_plan = models.CharField(max_length=100, default='Square root of N + 1 (WHO/GMP)')

    # Testing details
    analyst = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='conducted_tests')
    testing_completed_at = models.DateTimeField(null=True, blank=True)
    overall_test_result = models.CharField(max_length=20, choices=(('PENDING', 'Pending'), ('PASS', 'Passes All Tests'), ('FAIL', 'Out of Specification (OOS)')), default='PENDING')

    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default='PENDING_SAMPLING', db_index=True)

    def save(self, *args, **kwargs):
        if not self.document_no:
            self.document_no = DocumentSequence.get_next_number('QC', self.branch)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.document_no} - {self.lot.lot_number} ({self.status})"


class QCTestResult(ERPBaseModel):
    """
    Individual analytical test result against a specification parameter.
    """
    inspection = models.ForeignKey(QCInspectionRequest, on_delete=models.CASCADE, related_name='test_results')
    parameter = models.ForeignKey(SpecificationParameter, on_delete=models.PROTECT)

    raw_result_value = models.CharField(max_length=255, help_text="Textual or numerical analytical result, e.g. 99.4%")
    numerical_value = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)
    is_compliant = models.BooleanField(default=True)
    is_oos = models.BooleanField(default=False, help_text="Out of Specification flag")
    remarks = models.CharField(max_length=255, blank=True)

    def clean(self):
        # Auto-check numeric limits
        if self.numerical_value is not None:
            if self.parameter.min_limit is not None and self.numerical_value < self.parameter.min_limit:
                self.is_compliant = False
                self.is_oos = True
            elif self.parameter.max_limit is not None and self.numerical_value > self.parameter.max_limit:
                self.is_compliant = False
                self.is_oos = True
            else:
                self.is_compliant = True
                self.is_oos = False

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)


class QADispositionRecord(ERPDocumentModel):
    """
    Formal Quality Assurance Batch Release / Rejection / Quarantine Hold.
    21 CFR Part 11 Attributable Electronic Approval with atomical inventory update.
    """
    DISPOSITION_CHOICES = (
        ('RELEASE', 'Authorized Batch Release to Commercial Stock'),
        ('REJECT', 'Rejected / Segregated for Destruction'),
        ('HOLD', 'Quarantine Hold (Pending Investigation)'),
    )

    inspection = models.OneToOneField(QCInspectionRequest, on_delete=models.PROTECT, related_name='qa_disposition')
    lot = models.ForeignKey(InventoryLot, on_delete=models.PROTECT, related_name='qa_dispositions')
    disposition = models.CharField(max_length=20, choices=DISPOSITION_CHOICES)
    disposition_date = models.DateTimeField(default=timezone.now)

    authorized_qa_person = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='executed_qa_dispositions')
    decision_reason = models.TextField(help_text="Detailed regulatory rationale for disposition")
    coa_number = models.CharField(max_length=100, blank=True, help_text="Certificate of Analysis (COA) number")

    def clean(self):
        super().clean()
        if self.disposition == 'RELEASE' and not str(self.coa_number).strip():
            raise ValidationError({
                'coa_number': "A valid Certificate of Analysis (COA) number is mandatory to release a pharmaceutical batch."
            })
        if not str(self.decision_reason).strip():
            raise ValidationError({
                'decision_reason': "Attributable 21 CFR Part 11 regulatory rationale is mandatory."
            })

    def save(self, *args, **kwargs):
        self.clean()
        if not self.document_no:
            self.document_no = DocumentSequence.get_next_number('QA-DISP', self.branch)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.document_no} - Lot: {self.lot.lot_number} -> {self.disposition}"


class QualityDeviation(ERPDocumentModel):
    """
    GMP Deviation / Incident Management Record.
    """
    SEVERITY_CHOICES = (
        ('MINOR', 'Minor (No direct product quality impact)'),
        ('MAJOR', 'Major (Potential impact, requires full investigation)'),
        ('CRITICAL', 'Critical (Direct regulatory/patient safety risk)'),
    )

    deviation_title = models.CharField(max_length=255)
    severity = models.CharField(max_length=20, choices=SEVERITY_CHOICES, default='MINOR')
    affected_lot = models.ForeignKey(InventoryLot, null=True, blank=True, on_delete=models.SET_NULL)
    immediate_containment = models.TextField(help_text="Immediate action taken to contain material")
    root_cause = models.TextField(blank=True, help_text="5-Why or Fishbone root cause analysis")
    impact_assessment = models.TextField(blank=True)
    status = models.CharField(max_length=30, default='OPEN')

    def save(self, *args, **kwargs):
        if not self.document_no:
            self.document_no = DocumentSequence.get_next_number('DEV', self.branch)
        super().save(*args, **kwargs)


class ProductRecall(ERPDocumentModel):
    """
    Product Batch Recall Management with customer notifications and reconciliation.
    """
    CLASS_CHOICES = (
        ('CLASS_I', 'Class I (Dangerous / Defective with health hazard)'),
        ('CLASS_II', 'Class II (Temporary or medically reversible hazard)'),
        ('CLASS_III', 'Class III (Unlikely to cause adverse health consequences)'),
    )

    lot = models.ForeignKey(InventoryLot, on_delete=models.PROTECT, related_name='recalls')
    classification = models.CharField(max_length=20, choices=CLASS_CHOICES)
    recall_reason = models.TextField()
    total_distributed_qty = models.DecimalField(max_digits=14, decimal_places=4, default=Decimal('0.0000'))
    total_reconciled_qty = models.DecimalField(max_digits=14, decimal_places=4, default=Decimal('0.0000'))
    status = models.CharField(max_length=30, default='INITIATED')

    def clean(self):
        super().clean()
        if self.total_reconciled_qty is not None and self.total_distributed_qty is not None:
            if self.total_reconciled_qty > self.total_distributed_qty:
                raise ValidationError({
                    'total_reconciled_qty': "Reconciled recalled quantity cannot exceed total distributed quantity."
                })

    def save(self, *args, **kwargs):
        self.clean()
        if not self.document_no:
            self.document_no = DocumentSequence.get_next_number('RECALL', self.branch)
        super().save(*args, **kwargs)
