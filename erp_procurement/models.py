import uuid
from decimal import Decimal
from django.db import models, transaction
from django.conf import settings
from django.utils import timezone
from django.core.validators import MinValueValidator
from django.core.exceptions import ValidationError
from erp_core.models import ERPBaseModel, ERPDocumentModel, Branch, DocumentSequence
from erp_masters.models import ItemMaster, SupplierMaster, UnitOfMeasure, Warehouse, StorageBin


class PurchaseRequisition(ERPDocumentModel):
    """
    Internal demand requisition for Raw Materials, Packaging, or Lab Consumables.
    """
    PRIORITY_CHOICES = (
        ('LOW', 'Low Priority'),
        ('MEDIUM', 'Medium Priority'),
        ('HIGH', 'High / Urgent'),
        ('CRITICAL', 'Critical (Production Stoppage)'),
    )

    STATUS_CHOICES = (
        ('DRAFT', 'Draft'),
        ('SUBMITTED', 'Submitted for Department Approval'),
        ('APPROVED', 'Approved by HOD / Finance'),
        ('REJECTED', 'Rejected'),
        ('PO_CREATED', 'PO Generated'),
    )

    department = models.CharField(max_length=100, default='Production / QA')
    need_by_date = models.DateField()
    priority = models.CharField(max_length=20, choices=PRIORITY_CHOICES, default='MEDIUM')
    purpose = models.TextField(help_text="Production batch reference or stock reorder reason")
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default='DRAFT', db_index=True)

    def save(self, *args, **kwargs):
        if not self.document_no:
            self.document_no = DocumentSequence.get_next_number('PR', self.branch)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.document_no} [{self.status}]"


class PurchaseRequisitionLine(ERPBaseModel):
    requisition = models.ForeignKey(PurchaseRequisition, on_delete=models.CASCADE, related_name='lines')
    item = models.ForeignKey(ItemMaster, on_delete=models.PROTECT)
    quantity = models.DecimalField(max_digits=14, decimal_places=4, validators=[MinValueValidator(Decimal('0.0001'))])
    uom = models.ForeignKey(UnitOfMeasure, on_delete=models.PROTECT)
    estimated_rate = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'))
    suggested_supplier = models.ForeignKey(SupplierMaster, null=True, blank=True, on_delete=models.SET_NULL)
    notes = models.CharField(max_length=255, blank=True)

    def __str__(self):
        return f"{self.item.item_code} - {self.quantity} {self.uom.code}"


class PurchaseOrder(ERPDocumentModel):
    """
    Legally binding commercial order issued to qualified suppliers.
    Approval gated by financial threshold.
    """
    STATUS_CHOICES = (
        ('DRAFT', 'Draft'),
        ('SUBMITTED', 'Submitted for Threshold Approval'),
        ('APPROVED', 'Approved by Purchase Head'),
        ('SENT_TO_SUPPLIER', 'Sent & Acknowledged by Vendor'),
        ('PARTIALLY_RECEIVED', 'Partially Received'),
        ('COMPLETED', 'Fully Received & Closed'),
        ('CANCELLED', 'Cancelled'),
    )

    supplier = models.ForeignKey(SupplierMaster, on_delete=models.PROTECT, related_name='purchase_orders')
    requisition = models.ForeignKey(PurchaseRequisition, null=True, blank=True, on_delete=models.SET_NULL, related_name='purchase_orders')
    order_date = models.DateField(default=timezone.now)
    expected_delivery_date = models.DateField()

    currency = models.CharField(max_length=10, default='INR')
    payment_terms = models.CharField(max_length=100, default='Net 30 Days')
    subtotal = models.DecimalField(max_digits=16, decimal_places=2, default=Decimal('0.00'))
    tax_total = models.DecimalField(max_digits=16, decimal_places=2, default=Decimal('0.00'))
    grand_total = models.DecimalField(max_digits=16, decimal_places=2, default=Decimal('0.00'))
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default='DRAFT', db_index=True)

    def clean(self):
        super().clean()
        if self.order_date and self.expected_delivery_date:
            if self.expected_delivery_date < self.order_date:
                raise ValidationError({
                    'expected_delivery_date': "Expected delivery date cannot be before order date."
                })
        if self.supplier and self.supplier.status in ['DISQUALIFIED', 'BLOCKED']:
            raise ValidationError({
                'supplier': f"Cannot issue Purchase Order to supplier {self.supplier.legal_name} with status {self.supplier.status}."
            })

    def save(self, *args, **kwargs):
        self.clean()
        if not self.document_no:
            self.document_no = DocumentSequence.get_next_number('PO', self.branch)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.document_no} - {self.supplier.legal_name} ({self.status}) Total: ₹{self.grand_total}"


class PurchaseOrderLine(ERPBaseModel):
    order = models.ForeignKey(PurchaseOrder, on_delete=models.CASCADE, related_name='lines')
    item = models.ForeignKey(ItemMaster, on_delete=models.PROTECT)
    ordered_qty = models.DecimalField(max_digits=14, decimal_places=4, validators=[MinValueValidator(Decimal('0.0001'))])
    uom = models.ForeignKey(UnitOfMeasure, on_delete=models.PROTECT)
    rate = models.DecimalField(max_digits=14, decimal_places=2, validators=[MinValueValidator(Decimal('0.00'))])
    discount_percent = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('0.00'))
    tax_percent = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('12.00'))
    line_total = models.DecimalField(max_digits=16, decimal_places=2, default=Decimal('0.00'))

    received_qty = models.DecimalField(max_digits=14, decimal_places=4, default=Decimal('0.0000'))
    invoiced_qty = models.DecimalField(max_digits=14, decimal_places=4, default=Decimal('0.0000'))

    def clean(self):
        super().clean()
        if self.discount_percent is not None and (self.discount_percent < 0 or self.discount_percent > 100):
            raise ValidationError({'discount_percent': "Discount percentage must be between 0 and 100."})

    def save(self, *args, **kwargs):
        self.clean()
        base = self.ordered_qty * self.rate * (Decimal('1.00') - (self.discount_percent / Decimal('100.00')))
        tax = base * (self.tax_percent / Decimal('100.00'))
        self.line_total = base + tax
        super().save(*args, **kwargs)


class GoodsReceiptNote(ERPDocumentModel):
    """
    Warehouse Physical Inward Receipt against a Purchase Order.
    Critical compliance rule: Always lands materials in QUARANTINE stock.
    """
    STATUS_CHOICES = (
        ('QUARANTINED', 'Quarantined (Sampling / QC Pending)'),
        ('UNDER_INSPECTION', 'QC Testing Underway'),
        ('DISPOSITIONED', 'Quality Disposition Completed'),
        ('REJECTED', 'Whole Receipt Rejected'),
    )

    po = models.ForeignKey(PurchaseOrder, on_delete=models.PROTECT, related_name='grns')
    supplier = models.ForeignKey(SupplierMaster, on_delete=models.PROTECT)
    warehouse = models.ForeignKey(Warehouse, on_delete=models.PROTECT)

    delivery_challan_no = models.CharField(max_length=100)
    supplier_invoice_no = models.CharField(max_length=100, blank=True)
    supplier_invoice_date = models.DateField(null=True, blank=True)
    receipt_date = models.DateField(default=timezone.now)

    transporter_name = models.CharField(max_length=100, blank=True)
    vehicle_number = models.CharField(max_length=50, blank=True)
    temperature_on_arrival = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True, help_text="Cold-chain verification °C")

    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default='QUARANTINED', db_index=True)

    def save(self, *args, **kwargs):
        if not self.document_no:
            self.document_no = DocumentSequence.get_next_number('GRN', self.branch)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.document_no} (PO: {self.po.document_no}) - {self.status}"


class GoodsReceiptNoteLine(ERPBaseModel):
    """
    Individual item received, supplier batch reference, and quarantine lot link.
    """
    grn = models.ForeignKey(GoodsReceiptNote, on_delete=models.CASCADE, related_name='lines')
    po_line = models.ForeignKey(PurchaseOrderLine, on_delete=models.PROTECT, related_name='grn_lines')
    item = models.ForeignKey(ItemMaster, on_delete=models.PROTECT)

    supplier_batch_no = models.CharField(max_length=100)
    manufacturing_date = models.DateField()
    expiry_date = models.DateField()

    received_qty = models.DecimalField(max_digits=14, decimal_places=4, validators=[MinValueValidator(Decimal('0.0001'))])
    uom = models.ForeignKey(UnitOfMeasure, on_delete=models.PROTECT)
    bin = models.ForeignKey(StorageBin, null=True, blank=True, on_delete=models.SET_NULL, help_text="Quarantine Bin Location")

    # Quantities post QC disposition
    accepted_qty = models.DecimalField(max_digits=14, decimal_places=4, default=Decimal('0.0000'))
    rejected_qty = models.DecimalField(max_digits=14, decimal_places=4, default=Decimal('0.0000'))
    lot = models.ForeignKey('erp_inventory.InventoryLot', null=True, blank=True, on_delete=models.SET_NULL, related_name='grn_source_lines')

    def clean(self):
        super().clean()
        if self.manufacturing_date and self.expiry_date:
            if self.expiry_date <= self.manufacturing_date:
                raise ValidationError({'expiry_date': "GRN Line expiry date must be strictly after manufacturing date."})
        if self.received_qty is not None and self.received_qty <= Decimal('0'):
            raise ValidationError({'received_qty': "Received quantity must be greater than zero."})

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.item.item_code} | Batch {self.supplier_batch_no} | Rcvd: {self.received_qty} {self.uom.code}"
