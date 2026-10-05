import uuid
from decimal import Decimal
from django.db import models, transaction
from django.conf import settings
from django.utils import timezone
from django.core.validators import MinValueValidator
from django.core.exceptions import ValidationError
from erp_core.models import ERPBaseModel, ERPDocumentModel, DocumentSequence
from erp_masters.models import ItemMaster, CustomerMaster, UnitOfMeasure, Warehouse
from erp_inventory.models import InventoryLot, StockLedger


class SalesOrder(ERPDocumentModel):
    """
    Customer Sales Order in the Order-to-Cash cycle.
    """
    STATUS_CHOICES = (
        ('DRAFT', 'Draft Entry'),
        ('SUBMITTED', 'Submitted for Credit Check'),
        ('APPROVED', 'Credit Approved, Stock Reserved via FEFO'),
        ('PICKING', 'Pick List Generated'),
        ('DISPATCHED', 'Invoiced & Dispatched'),
        ('CANCELLED', 'Cancelled'),
    )

    customer = models.ForeignKey(CustomerMaster, on_delete=models.PROTECT, related_name='sales_orders')
    order_date = models.DateField(default=timezone.now)
    requested_delivery_date = models.DateField()

    subtotal = models.DecimalField(max_digits=16, decimal_places=2, default=Decimal('0.00'))
    tax_total = models.DecimalField(max_digits=16, decimal_places=2, default=Decimal('0.00'))
    grand_total = models.DecimalField(max_digits=16, decimal_places=2, default=Decimal('0.00'))

    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default='DRAFT', db_index=True)
    credit_override = models.BooleanField(default=False)
    credit_override_reason = models.TextField(blank=True)

    def clean(self):
        super().clean()
        if self.order_date and self.requested_delivery_date:
            if self.requested_delivery_date < self.order_date:
                raise ValidationError({
                    'requested_delivery_date': "Requested delivery date cannot be earlier than order date."
                })
        if self.credit_override and not str(self.credit_override_reason).strip():
            raise ValidationError({
                'credit_override_reason': "Credit override reason is mandatory when credit limit is bypassed."
            })
        if self.customer and getattr(self.customer, 'status', None) in ['BLOCKED', 'DISQUALIFIED', 'SUSPENDED']:
            raise ValidationError({
                'customer': f"Customer {self.customer.name} has inactive/suspended status and cannot place sales orders."
            })

    def save(self, *args, **kwargs):
        self.clean()
        if not self.document_no:
            self.document_no = DocumentSequence.get_next_number('SO', self.branch)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.document_no} - {self.customer.name} (₹{self.grand_total}) [{self.status}]"


class SalesOrderLine(ERPBaseModel):
    order = models.ForeignKey(SalesOrder, on_delete=models.CASCADE, related_name='lines')
    product = models.ForeignKey(ItemMaster, on_delete=models.PROTECT, limit_choices_to={'item_type': 'FINISHED_GOOD'})
    ordered_qty = models.DecimalField(max_digits=14, decimal_places=4, validators=[MinValueValidator(Decimal('0.0001'))])
    uom = models.ForeignKey(UnitOfMeasure, on_delete=models.PROTECT)

    unit_price = models.DecimalField(max_digits=14, decimal_places=2, validators=[MinValueValidator(Decimal('0.00'))])
    discount_percent = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('0.00'))
    tax_percent = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('12.00'))
    line_total = models.DecimalField(max_digits=16, decimal_places=2, default=Decimal('0.00'))

    def clean(self):
        super().clean()
        if self.discount_percent is not None and (self.discount_percent < 0 or self.discount_percent > 100):
            raise ValidationError({'discount_percent': "Discount percent must be between 0% and 100%."})

    def save(self, *args, **kwargs):
        self.clean()
        base = self.ordered_qty * self.unit_price * (Decimal('1.00') - (self.discount_percent / Decimal('100.00')))
        tax = base * (self.tax_percent / Decimal('100.00'))
        self.line_total = base + tax
        super().save(*args, **kwargs)


class SalesOrderLotAllocation(ERPBaseModel):
    """
    Exact pharmaceutical batches allocated to an order line using FEFO.
    """
    line = models.ForeignKey(SalesOrderLine, on_delete=models.CASCADE, related_name='lot_allocations')
    lot = models.ForeignKey(InventoryLot, on_delete=models.PROTECT)
    allocated_qty = models.DecimalField(max_digits=14, decimal_places=4)
    uom = models.ForeignKey(UnitOfMeasure, on_delete=models.PROTECT)
    is_dispatched = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.line.order.document_no} -> Lot {self.lot.lot_number}: {self.allocated_qty} {self.uom.code}"


class SalesDispatchInvoice(ERPDocumentModel):
    """
    Tax Invoice & Delivery Challan with transporter details and e-way bill number.
    """
    order = models.ForeignKey(SalesOrder, on_delete=models.PROTECT, related_name='invoices')
    customer = models.ForeignKey(CustomerMaster, on_delete=models.PROTECT)
    invoice_date = models.DateField(default=timezone.now)

    transporter_name = models.CharField(max_length=150, blank=True)
    docket_no = models.CharField(max_length=100, blank=True, help_text="Courier / Lorry Receipt (LR) number")
    vehicle_number = models.CharField(max_length=50, blank=True)
    eway_bill_no = models.CharField(max_length=50, blank=True, help_text="Government E-Way Bill Number")

    total_amount = models.DecimalField(max_digits=16, decimal_places=2)
    is_paid = models.BooleanField(default=False)

    def save(self, *args, **kwargs):
        if not self.document_no:
            self.document_no = DocumentSequence.get_next_number('INV', self.branch)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Invoice {self.document_no} for {self.customer.name} (₹{self.total_amount})"
