import uuid
from decimal import Decimal
from django.db import models, transaction
from django.conf import settings
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from erp_core.models import ERPBaseModel, ERPDocumentModel, Branch
from erp_masters.models import ItemMaster, Warehouse, StorageBin, UnitOfMeasure, SupplierMaster


class InventoryLot(ERPBaseModel):
    """
    Physical lot/batch of pharmaceutical material or finished product
    with strict status lifecycle gating.
    """
    STATUS_CHOICES = (
        ('QUARANTINE', 'Quarantine (Pending QC Inspection)'),
        ('AVAILABLE', 'Available / Released (Approved for use/sale)'),
        ('RESERVED', 'Reserved (Allocated to Order)'),
        ('REJECTED', 'Rejected (Failed QC / Segregated)'),
        ('BLOCKED', 'Blocked (Under Hold / Investigation)'),
        ('EXPIRED', 'Expired (Past Shelf Life)'),
        ('RECALLED', 'Recalled (Under Product Recall)'),
        ('IN_TRANSIT', 'In-Transit between sites'),
    )

    lot_number = models.CharField(max_length=60, unique=True, db_index=True)
    item = models.ForeignKey(ItemMaster, on_delete=models.PROTECT, related_name='inventory_lots')
    batch_no = models.CharField(max_length=60, db_index=True, help_text="Batch number (never recycled)")
    supplier_lot_no = models.CharField(max_length=100, blank=True)
    supplier = models.ForeignKey(SupplierMaster, null=True, blank=True, on_delete=models.SET_NULL)

    warehouse = models.ForeignKey(Warehouse, on_delete=models.PROTECT, related_name='lots')
    bin = models.ForeignKey(StorageBin, null=True, blank=True, on_delete=models.SET_NULL, related_name='lots')

    manufacturing_date = models.DateField()
    expiry_date = models.DateField(db_index=True)
    retest_date = models.DateField(null=True, blank=True)

    quantity_on_hand = models.DecimalField(max_digits=14, decimal_places=4, default=Decimal('0.0000'), validators=[MinValueValidator(Decimal('0.0000'))])
    quantity_reserved = models.DecimalField(max_digits=14, decimal_places=4, default=Decimal('0.0000'), validators=[MinValueValidator(Decimal('0.0000'))])
    uom = models.ForeignKey(UnitOfMeasure, on_delete=models.PROTECT)
    unit_cost = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'))

    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default='QUARANTINE', db_index=True)
    qc_reference = models.CharField(max_length=100, blank=True, help_text="QC Analytical Report Number / COA")
    released_at = models.DateTimeField(null=True, blank=True)
    released_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='released_lots')

    class Meta:
        ordering = ['expiry_date', 'lot_number']
        verbose_name = "Inventory Lot / Batch"
        verbose_name_plural = "Inventory Lots & Batches"

    @property
    def is_eligible_for_issue(self) -> bool:
        """Only released, unblocked, unexpired stock can be issued."""
        today = timezone.now().date()
        return self.status == 'AVAILABLE' and self.expiry_date >= today and self.quantity_available > 0

    @property
    def quantity_available(self) -> Decimal:
        return max(Decimal('0.0000'), self.quantity_on_hand - self.quantity_reserved)

    def clean(self):
        super().clean()
        if self.manufacturing_date and self.expiry_date:
            if self.expiry_date <= self.manufacturing_date:
                raise ValidationError({
                    'expiry_date': "Batch expiry date must be strictly after manufacturing date."
                })
        if self.retest_date and self.manufacturing_date:
            if self.retest_date < self.manufacturing_date:
                raise ValidationError({
                    'retest_date': "Retest date cannot be earlier than manufacturing date."
                })
        if self.quantity_reserved is not None and self.quantity_on_hand is not None:
            if self.quantity_reserved > self.quantity_on_hand:
                raise ValidationError({
                    'quantity_reserved': f"Reserved quantity ({self.quantity_reserved}) cannot exceed quantity on hand ({self.quantity_on_hand})."
                })
        if self.status == 'AVAILABLE' and self.expiry_date:
            today = timezone.now().date()
            if self.expiry_date < today:
                raise ValidationError({
                    'status': "Expired batch cannot be marked as AVAILABLE. Status must be EXPIRED or BLOCKED."
                })

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.lot_number} | {self.item.name} | Batch: {self.batch_no} [{self.status}] Qty: {self.quantity_on_hand} {self.uom.code}"


class StockLedger(models.Model):
    """
    Immutable Pharmaceutical Stock Movement Ledger.
    Every single gram/tablet moved must have a permanent, unalterable ledger entry.
    """
    TRANSACTION_TYPES = (
        ('GRN_RECEIPT', 'Goods Receipt Note (Quarantine Inward)'),
        ('QC_RELEASE', 'QC Inspection Release to Stock'),
        ('QC_REJECT', 'QC Inspection Rejection'),
        ('MATERIAL_ISSUE', 'Issue to Production Batch'),
        ('PRODUCTION_RECEIPT', 'Receipt of Finished Goods from Production'),
        ('TRANSFER_IN', 'Warehouse Transfer Inward'),
        ('TRANSFER_OUT', 'Warehouse Transfer Outward'),
        ('DISPATCH', 'Sales Dispatch / Customer Invoice'),
        ('CUSTOMER_RETURN', 'Customer Return Quarantine Inward'),
        ('ADJUSTMENT_PLUS', 'Approved Physical Count Positive Adjustment'),
        ('ADJUSTMENT_MINUS', 'Approved Physical Count Negative Adjustment'),
        ('RECALL_BLOCK', 'Batch Regulatory Recall Block'),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    timestamp = models.DateTimeField(default=timezone.now, db_index=True)
    transaction_type = models.CharField(max_length=30, choices=TRANSACTION_TYPES, db_index=True)
    document_no = models.CharField(max_length=64, db_index=True, help_text="Source Document (PO, GRN, BMR, INV)")

    lot = models.ForeignKey(InventoryLot, on_delete=models.PROTECT, related_name='ledger_entries')
    item = models.ForeignKey(ItemMaster, on_delete=models.PROTECT, related_name='stock_movements')

    from_warehouse = models.ForeignKey(Warehouse, null=True, blank=True, on_delete=models.PROTECT, related_name='stock_out_entries')
    from_bin = models.ForeignKey(StorageBin, null=True, blank=True, on_delete=models.PROTECT, related_name='bin_out_entries')
    to_warehouse = models.ForeignKey(Warehouse, null=True, blank=True, on_delete=models.PROTECT, related_name='stock_in_entries')
    to_bin = models.ForeignKey(StorageBin, null=True, blank=True, on_delete=models.PROTECT, related_name='bin_in_entries')

    quantity = models.DecimalField(max_digits=14, decimal_places=4, validators=[MinValueValidator(Decimal('0.0001'))])
    uom = models.ForeignKey(UnitOfMeasure, on_delete=models.PROTECT)
    unit_cost = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'))
    total_value = models.DecimalField(max_digits=16, decimal_places=2, default=Decimal('0.00'))

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    reason = models.TextField(blank=True)

    class Meta:
        ordering = ['-timestamp']
        verbose_name = "Stock Ledger Entry"
        verbose_name_plural = "Stock Ledger Entries"

    def __str__(self):
        return f"[{self.timestamp.strftime('%Y-%m-%d %H:%M')}] {self.transaction_type} {self.quantity} {self.uom.code} of {self.item.item_code} ({self.document_no})"

    def save(self, *args, **kwargs):
        if self.pk and StockLedger.objects.filter(pk=self.pk).exists():
            raise ValidationError("Stock ledger entries are immutable and cannot be updated.")
        self.total_value = self.quantity * self.unit_cost
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Stock ledger records are permanent and can NEVER be deleted.")


class CycleCountSession(ERPDocumentModel):
    """
    Physical Inventory Verification / Cycle Counting session with snapshot freezing.
    """
    STATUS_CHOICES = (
        ('DRAFT', 'Draft'),
        ('FROZEN', 'Scope Frozen for Count'),
        ('IN_PROGRESS', 'Counting in Progress'),
        ('SUBMITTED', 'Counts Submitted, Variance Calculated'),
        ('APPROVED', 'Variances Approved by Finance/QA'),
        ('POSTED', 'Adjustments Posted to Stock Ledger'),
    )

    warehouse = models.ForeignKey(Warehouse, on_delete=models.PROTECT)
    zone_filter = models.CharField(max_length=100, blank=True, help_text="Specific zone or blank for full warehouse")
    blind_count = models.BooleanField(default=True, help_text="Counters cannot see expected system quantity")
    count_status = models.CharField(max_length=30, choices=STATUS_CHOICES, default='DRAFT')

    def __str__(self):
        return f"{self.document_no} ({self.warehouse.code}) [{self.count_status}]"


class CycleCountLine(ERPBaseModel):
    """
    Item and lot level line item for a cycle count session.
    """
    session = models.ForeignKey(CycleCountSession, on_delete=models.CASCADE, related_name='lines')
    lot = models.ForeignKey(InventoryLot, on_delete=models.PROTECT)
    item = models.ForeignKey(ItemMaster, on_delete=models.PROTECT)
    bin = models.ForeignKey(StorageBin, null=True, blank=True, on_delete=models.SET_NULL)

    system_quantity = models.DecimalField(max_digits=14, decimal_places=4)
    counted_quantity = models.DecimalField(max_digits=14, decimal_places=4, null=True, blank=True)
    variance_quantity = models.DecimalField(max_digits=14, decimal_places=4, default=Decimal('0.0000'))
    recount_required = models.BooleanField(default=False)
    counter_user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    remarks = models.CharField(max_length=255, blank=True)

    def clean(self):
        super().clean()
        if self.system_quantity is not None and self.system_quantity < 0:
            raise ValidationError({'system_quantity': "System inventory quantity cannot be negative."})
        if self.counted_quantity is not None and self.counted_quantity < 0:
            raise ValidationError({'counted_quantity': "Physical counted quantity cannot be negative."})

    def calculate_variance(self):
        if self.counted_quantity is not None:
            self.variance_quantity = self.counted_quantity - self.system_quantity
            # Flag recount if variance exceeds 1% or abs > 1
            if abs(self.variance_quantity) > Decimal('0.01'):
                self.recount_required = True
        return self.variance_quantity
