import uuid
from decimal import Decimal
from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator
from django.core.exceptions import ValidationError
from erp_core.models import ERPBaseModel, Branch


class UnitOfMeasure(ERPBaseModel):
    """
    Standard pharmaceutical Units of Measure (kg, gm, mg, Litre, ml, Vial, Strip, Box, Nos).
    """
    code = models.CharField(max_length=20, unique=True, help_text="e.g. KG, GM, MG, LTR, ML, TAB, CAP, STRIP")
    name = models.CharField(max_length=100)
    symbol = models.CharField(max_length=10)
    is_discrete = models.BooleanField(default=False, help_text="True for countable items (Tablets, Strips)")

    class Meta:
        verbose_name = "Unit of Measure (UOM)"
        verbose_name_plural = "Units of Measure"
        ordering = ['code']

    def __str__(self):
        return f"{self.name} ({self.code})"


class UOMConversion(ERPBaseModel):
    """
    Conversion factor between units: from_uom * conversion_factor = to_uom.
    e.g. 1 KG = 1000 GM (conversion_factor = 1000).
    """
    from_uom = models.ForeignKey(UnitOfMeasure, on_delete=models.CASCADE, related_name='conversions_from')
    to_uom = models.ForeignKey(UnitOfMeasure, on_delete=models.CASCADE, related_name='conversions_to')
    conversion_factor = models.DecimalField(max_digits=18, decimal_places=6, validators=[MinValueValidator(Decimal('0.000001'))])

    class Meta:
        unique_together = ('from_uom', 'to_uom')

    def clean(self):
        super().clean()
        if self.from_uom_id and self.to_uom_id and self.from_uom_id == self.to_uom_id:
            raise ValidationError("Cannot define conversion between the same unit of measure.")

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"1 {self.from_uom.code} = {self.conversion_factor} {self.to_uom.code}"


class Warehouse(ERPBaseModel):
    """
    Warehouse location scoped to a branch with pharmaceutical zoning.
    """
    WAREHOUSE_TYPE_CHOICES = (
        ('GENERAL', 'General Ambient Warehouse'),
        ('COLD_CHAIN', 'Cold Chain (2°C - 8°C)'),
        ('QUARANTINE', 'Quarantine Holding Area'),
        ('FINISHED_GOODS', 'Finished Goods Central'),
        ('RAW_MATERIALS', 'Raw Materials / Active Ingredients Bay'),
    )

    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, related_name='warehouses')
    code = models.CharField(max_length=30, unique=True)
    name = models.CharField(max_length=150)
    warehouse_type = models.CharField(max_length=30, choices=WAREHOUSE_TYPE_CHOICES, default='GENERAL')
    controlled_access = models.BooleanField(default=False, help_text="Requires specialized authorization (e.g. Narcotic/High-value)")
    temperature_min = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True, help_text="Min Temp °C")
    temperature_max = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True, help_text="Max Temp °C")
    humidity_max = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True, help_text="Max RH %")

    def clean(self):
        super().clean()
        if self.temperature_min is not None and self.temperature_max is not None:
            if self.temperature_max < self.temperature_min:
                raise ValidationError({
                    'temperature_max': "Maximum temperature cannot be lower than minimum temperature."
                })

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"[{self.branch.code}] {self.name} ({self.code})"


class StorageBin(ERPBaseModel):
    """
    Specific rack/shelf/bin inside a warehouse zone for lot-level putaway.
    """
    warehouse = models.ForeignKey(Warehouse, on_delete=models.CASCADE, related_name='bins')
    zone = models.CharField(max_length=50, help_text="e.g. Quarantine Zone, Sampling Booth, Released Store, Cold Room")
    bin_code = models.CharField(max_length=50)
    capacity_kg = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)

    class Meta:
        unique_together = ('warehouse', 'bin_code')

    def __str__(self):
        return f"{self.warehouse.code} -> {self.zone} / {self.bin_code}"


class ItemMaster(ERPBaseModel):
    """
    Master record for Raw Materials, APIs, Excipients, Packaging, WIP, and Finished Goods.
    """
    ITEM_TYPE_CHOICES = (
        ('API', 'Active Pharmaceutical Ingredient (API)'),
        ('EXCIPIENT', 'Excipient / Chemical'),
        ('RAW_MATERIAL', 'Raw Material'),
        ('PACKAGING_PRIMARY', 'Primary Packaging (Alu/PVC, Bottles, Vials)'),
        ('PACKAGING_SECONDARY', 'Secondary Packaging (Cartons, Shippers, Leaflets)'),
        ('WIP', 'Work-in-Progress (Bulk Granules, Uncoated Tabs)'),
        ('FINISHED_GOOD', 'Finished Pharmaceutical Product'),
        ('CONSUMABLE', 'Lab / Factory Consumable'),
    )

    STORAGE_CONDITIONS = (
        ('ROOM_TEMP', 'Controlled Room Temperature (20°C - 25°C)'),
        ('COOL', 'Cool Storage (8°C - 15°C)'),
        ('COLD', 'Refrigerated Cold Chain (2°C - 8°C)'),
        ('DEEP_FREEZE', 'Deep Freeze (-20°C)'),
        ('PROTECT_LIGHT', 'Protect from light and moisture'),
    )

    item_code = models.CharField(max_length=50, unique=True, db_index=True)
    name = models.CharField(max_length=200, db_index=True)
    generic_name = models.CharField(max_length=200, blank=True, help_text="Chemical / Generic formulation name")
    item_type = models.CharField(max_length=30, choices=ITEM_TYPE_CHOICES, db_index=True)
    dosage_form = models.CharField(max_length=100, blank=True, help_text="e.g. Tablet, Capsule, Syrup, Injectable")
    strength = models.CharField(max_length=100, blank=True, help_text="e.g. 500mg, 10mg/5ml")
    category = models.CharField(max_length=100, blank=True, help_text="Therapeutic category, e.g. Antibiotic, Analgesic")

    base_uom = models.ForeignKey(UnitOfMeasure, on_delete=models.PROTECT, related_name='items_base')
    purchase_uom = models.ForeignKey(UnitOfMeasure, on_delete=models.PROTECT, related_name='items_purchase', null=True, blank=True)
    issue_uom = models.ForeignKey(UnitOfMeasure, on_delete=models.PROTECT, related_name='items_issue', null=True, blank=True)

    barcode = models.CharField(max_length=100, blank=True, null=True, unique=True)
    storage_condition = models.CharField(max_length=30, choices=STORAGE_CONDITIONS, default='ROOM_TEMP')
    shelf_life_days = models.PositiveIntegerField(help_text="Standard shelf life in days from manufacturing date")
    retest_interval_days = models.PositiveIntegerField(null=True, blank=True, help_text="Retest period for active chemicals/APIs")

    reorder_min = models.DecimalField(max_digits=14, decimal_places=4, default=Decimal('0.0000'))
    reorder_max = models.DecimalField(max_digits=14, decimal_places=4, default=Decimal('0.0000'))

    tax_rate = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('12.00'), help_text="GST / Tax percentage")
    standard_cost = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'))
    mrp = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'), help_text="Max Retail Price for Finished Goods")

    active_flag = models.BooleanField(default=True)

    def clean(self):
        if self.reorder_max < self.reorder_min:
            raise ValidationError("Reorder max cannot be less than reorder min.")

    def __str__(self):
        return f"[{self.item_code}] {self.name} ({self.get_item_type_display()})"


class SupplierMaster(ERPBaseModel):
    """
    Approved and Qualified Vendors for APIs, Excipients, Packaging, and Lab Supplies.
    """
    STATUS_CHOICES = (
        ('QUALIFIED', 'Fully Qualified / GMP Audited'),
        ('UNDER_EVALUATION', 'Under Audit / Evaluation'),
        ('DISQUALIFIED', 'Disqualified / GMP Non-Compliant'),
        ('BLOCKED', 'Blocked for Commercial / Quality issues'),
    )

    supplier_code = models.CharField(max_length=50, unique=True, db_index=True)
    legal_name = models.CharField(max_length=200)
    trade_name = models.CharField(max_length=200, blank=True)
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default='UNDER_EVALUATION', db_index=True)

    gstin = models.CharField(max_length=20, blank=True)
    pan = models.CharField(max_length=20, blank=True)
    address = models.TextField()
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=100)
    country = models.CharField(max_length=100, default='India')

    contact_person = models.CharField(max_length=100, blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=30, blank=True)

    payment_terms_days = models.PositiveIntegerField(default=30)
    currency = models.CharField(max_length=10, default='INR')

    # Restricted Banking Details
    bank_name = models.CharField(max_length=150, blank=True)
    bank_account_no = models.CharField(max_length=50, blank=True)
    bank_ifsc = models.CharField(max_length=20, blank=True)

    # QA Compliance Fields
    gmp_certificate_no = models.CharField(max_length=100, blank=True)
    qualification_expiry = models.DateField(null=True, blank=True)

    def is_eligible_for_po(self):
        return self.status == 'QUALIFIED' and self.is_active

    def __str__(self):
        return f"[{self.supplier_code}] {self.legal_name} ({self.status})"


class CustomerMaster(ERPBaseModel):
    """
    Hospitals, Stockists, Distributors, Pharmacies, and Export Clients.
    """
    CUSTOMER_TYPE_CHOICES = (
        ('DISTRIBUTOR', 'Wholesale Distributor'),
        ('STOCKIST', 'Carrying & Forwarding (C&F) Stockist'),
        ('HOSPITAL', 'Hospital / Medical Institute'),
        ('PHARMACY', 'Retail Pharmacy / Chemist'),
        ('CLINIC', 'Doctor Clinic / Nursing Home'),
        ('GOVERNMENT', 'Government Supply / Tender'),
        ('EXPORT', 'International / Export Buyer'),
    )

    customer_code = models.CharField(max_length=50, unique=True, db_index=True)
    name = models.CharField(max_length=200, db_index=True)
    customer_type = models.CharField(max_length=30, choices=CUSTOMER_TYPE_CHOICES)

    billing_address = models.TextField()
    shipping_address = models.TextField(blank=True)
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=100)
    country = models.CharField(max_length=100, default='India')
    gstin = models.CharField(max_length=20, blank=True)
    pan = models.CharField(max_length=20, blank=True)

    # Drug Licensing (Mandatory in India / Pharma regulations)
    drug_license_20b = models.CharField(max_length=100, blank=True, help_text="Wholesale Form 20-B")
    drug_license_21b = models.CharField(max_length=100, blank=True, help_text="Form 21-B for Schedules C & C(1)")
    license_expiry_date = models.DateField(null=True, blank=True)

    contact_person = models.CharField(max_length=100, blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=30, blank=True)

    credit_limit = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'))
    current_balance = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'))
    payment_terms_days = models.PositiveIntegerField(default=30)
    credit_hold = models.BooleanField(default=False, help_text="Hold orders if invoices overdue or limit exceeded")

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"[{self.customer_code}] {self.name}"


class QualitySpecification(ERPBaseModel):
    """
    Standard Finished Product / Raw Material Quality Specification (Pharmacopoeia: IP / BP / USP / In-House).
    """
    spec_code = models.CharField(max_length=50, unique=True)
    item = models.ForeignKey(ItemMaster, on_delete=models.CASCADE, related_name='specifications')
    version = models.PositiveIntegerField(default=1)
    pharmacopoeia = models.CharField(max_length=50, default='IP', help_text="e.g. IP, BP, USP, In-House")
    effective_date = models.DateField()
    is_approved = models.BooleanField(default=False)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='approved_specifications'
    )

    class Meta:
        unique_together = ('item', 'version')

    def __str__(self):
        return f"SPEC-{self.spec_code} v{self.version} ({self.item.name})"


class SpecificationParameter(ERPBaseModel):
    """
    Individual test criteria within a quality specification.
    e.g. Assay (95.0% - 105.0%), Dissolution (>85% in 30min), Related Substances (<0.2%), pH (6.0 - 7.5).
    """
    specification = models.ForeignKey(QualitySpecification, on_delete=models.CASCADE, related_name='parameters')
    sequence = models.PositiveIntegerField(default=1)
    parameter_name = models.CharField(max_length=150, help_text="e.g. Description, Identification, Assay, Dissolution, pH")
    test_method = models.CharField(max_length=100, blank=True, help_text="e.g. HPLC, UV, Titration, Karl Fischer")
    acceptance_criteria = models.TextField(help_text="Textual requirement or specification")
    min_limit = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)
    max_limit = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)
    unit = models.CharField(max_length=30, blank=True, help_text="%, mg/ml, pH, etc.")
    is_critical = models.BooleanField(default=True, help_text="Critical Quality Attribute (CQA)")

    class Meta:
        ordering = ['sequence']

    def __str__(self):
        return f"{self.parameter_name} ({self.specification.spec_code})"


class BOMHeader(ERPBaseModel):
    """
    Master Bill of Materials / Master Formula Record (MFR) for batch production.
    """
    bom_code = models.CharField(max_length=50, unique=True)
    product = models.ForeignKey(ItemMaster, on_delete=models.CASCADE, related_name='boms', limit_choices_to={'item_type__in': ['WIP', 'FINISHED_GOOD']})
    version = models.PositiveIntegerField(default=1)
    batch_size = models.DecimalField(max_digits=14, decimal_places=4, help_text="Standard batch quantity")
    batch_uom = models.ForeignKey(UnitOfMeasure, on_delete=models.PROTECT)
    effective_from = models.DateField()
    effective_to = models.DateField(null=True, blank=True)
    status = models.CharField(
        max_length=30,
        choices=(('DRAFT', 'Draft'), ('APPROVED', 'Approved & Released'), ('OBSOLETE', 'Obsolete')),
        default='DRAFT'
    )
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='approved_boms')
    approved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ('product', 'version')

    def __str__(self):
        return f"BOM: {self.bom_code} v{self.version} for {self.product.name} (Batch: {self.batch_size} {self.batch_uom.code})"


class BOMLine(ERPBaseModel):
    """
    Raw material / API / Excipient / Packaging component in a BOM.
    """
    bom = models.ForeignKey(BOMHeader, on_delete=models.CASCADE, related_name='lines')
    component = models.ForeignKey(ItemMaster, on_delete=models.PROTECT, related_name='used_in_boms')
    quantity = models.DecimalField(max_digits=14, decimal_places=4, validators=[MinValueValidator(Decimal('0.0001'))])
    uom = models.ForeignKey(UnitOfMeasure, on_delete=models.PROTECT)
    tolerance_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('0.00'), help_text="Permitted weighing tolerance %")
    stage_name = models.CharField(max_length=100, default='Dispensing / Granulation', help_text="Manufacturing stage where consumed")

    def __str__(self):
        return f"{self.component.name}: {self.quantity} {self.uom.code}"
