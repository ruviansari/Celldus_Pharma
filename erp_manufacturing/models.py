import uuid
from decimal import Decimal
from django.db import models, transaction
from django.conf import settings
from django.utils import timezone
from django.core.validators import MinValueValidator
from django.core.exceptions import ValidationError
from erp_core.models import ERPBaseModel, ERPDocumentModel, DocumentSequence
from erp_masters.models import ItemMaster, BOMHeader, UnitOfMeasure, Warehouse, StorageBin
from erp_inventory.models import InventoryLot, StockLedger


class ProductionOrder(ERPDocumentModel):
    """
    Manufacturing Batch Order / Electronic Batch Production Record (BMR/BPR).
    """
    STATUS_CHOICES = (
        ('DRAFT', 'Draft Planning'),
        ('RELEASED', 'Supervisor Released (BMR Issued)'),
        ('IN_PROGRESS', 'Manufacturing In-Progress'),
        ('COMPLETED', 'Batch Completed, Submitted to QC'),
        ('CLOSED', 'QA Dispositioned & Closed'),
        ('CANCELLED', 'Cancelled'),
    )

    product = models.ForeignKey(ItemMaster, on_delete=models.PROTECT, limit_choices_to={'item_type__in': ['WIP', 'FINISHED_GOOD']})
    bom = models.ForeignKey(BOMHeader, on_delete=models.PROTECT)
    batch_no = models.CharField(max_length=60, unique=True, db_index=True)

    planned_qty = models.DecimalField(max_digits=14, decimal_places=4, validators=[MinValueValidator(Decimal('0.0001'))])
    actual_produced_qty = models.DecimalField(max_digits=14, decimal_places=4, default=Decimal('0.0000'))
    scrap_qty = models.DecimalField(max_digits=14, decimal_places=4, default=Decimal('0.0000'))
    uom = models.ForeignKey(UnitOfMeasure, on_delete=models.PROTECT)

    target_warehouse = models.ForeignKey(Warehouse, on_delete=models.PROTECT)
    target_bin = models.ForeignKey(StorageBin, null=True, blank=True, on_delete=models.SET_NULL)

    manufacturing_date = models.DateField(default=timezone.now)
    expiry_date = models.DateField()

    planned_start_date = models.DateField()
    planned_end_date = models.DateField()
    actual_start_time = models.DateTimeField(null=True, blank=True)
    actual_end_time = models.DateTimeField(null=True, blank=True)

    yield_percentage = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal('0.00'))
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default='DRAFT', db_index=True)

    # Finished lot created post production (lands in QUARANTINE until QA release)
    finished_lot = models.ForeignKey(InventoryLot, null=True, blank=True, on_delete=models.SET_NULL, related_name='production_source')

    def clean(self):
        super().clean()
        if self.manufacturing_date and self.expiry_date:
            if self.expiry_date <= self.manufacturing_date:
                raise ValidationError({
                    'expiry_date': "Batch expiry date must be strictly after manufacturing date."
                })
        if self.planned_start_date and self.planned_end_date:
            if self.planned_end_date < self.planned_start_date:
                raise ValidationError({
                    'planned_end_date': "Planned end date cannot be earlier than planned start date."
                })
        if self.planned_qty is not None and self.planned_qty <= 0:
            raise ValidationError({
                'planned_qty': "Planned quantity must be greater than zero."
            })

    def save(self, *args, **kwargs):
        self.clean()
        if not self.document_no:
            self.document_no = DocumentSequence.get_next_number('PROD', self.branch)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.document_no} | Batch: {self.batch_no} | {self.product.name} ({self.status})"


class BatchMaterialConsumption(ERPBaseModel):
    """
    Traceability record of exact raw material lots dispensed and consumed in a batch.
    """
    order = models.ForeignKey(ProductionOrder, on_delete=models.CASCADE, related_name='material_consumptions')
    component = models.ForeignKey(ItemMaster, on_delete=models.PROTECT)
    lot = models.ForeignKey(InventoryLot, on_delete=models.PROTECT)
    standard_required_qty = models.DecimalField(max_digits=14, decimal_places=4)
    actual_consumed_qty = models.DecimalField(max_digits=14, decimal_places=4)
    uom = models.ForeignKey(UnitOfMeasure, on_delete=models.PROTECT)
    dispensed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    dispensed_at = models.DateTimeField(default=timezone.now)
    variance_reason = models.CharField(max_length=255, blank=True)

    def __str__(self):
        return f"{self.order.batch_no} -> {self.component.item_code}: {self.actual_consumed_qty} {self.uom.code} from Lot {self.lot.lot_number}"


class BatchProcessStep(ERPBaseModel):
    """
    Step-by-step electronic BMR stage execution (e.g. Dispensing, Sifting, Granulation, Compression, Coating, Packaging).
    """
    order = models.ForeignKey(ProductionOrder, on_delete=models.CASCADE, related_name='process_steps')
    sequence = models.PositiveIntegerField(default=1)
    step_name = models.CharField(max_length=150)
    sop_reference = models.CharField(max_length=100, blank=True, help_text="Standard Operating Procedure code")
    equipment_id = models.CharField(max_length=100, blank=True)

    operator = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='operated_steps')
    verified_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='verified_steps')

    start_time = models.DateTimeField(null=True, blank=True)
    end_time = models.DateTimeField(null=True, blank=True)
    is_completed = models.BooleanField(default=False)
    in_process_check_notes = models.TextField(blank=True)

    class Meta:
        ordering = ['sequence']

    def __str__(self):
        return f"{self.order.batch_no} - Step {self.sequence}: {self.step_name}"
