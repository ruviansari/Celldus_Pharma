import datetime
from decimal import Decimal
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.utils import timezone

from erp_core.models import Branch, ERPUserRole, DocumentSequence
from erp_masters.models import (
    UnitOfMeasure, UOMConversion, Warehouse, StorageBin,
    ItemMaster, SupplierMaster, CustomerMaster,
    QualitySpecification, SpecificationParameter,
    BOMHeader, BOMLine
)
from erp_inventory.models import InventoryLot, StockLedger
from erp_finance.models import ChartOfAccount

User = get_user_model()


class Command(BaseCommand):
    help = "Seeds initial production baseline for Celldus Pharma ERP"

    def handle(self, *args, **options):
        self.stdout.write("Initializing Celldus Pharma ERP Baseline Data...")

        # 1. Branch / Manufacturing Site
        site, _ = Branch.objects.get_or_create(
            code="SITE-01",
            defaults={
                "name": "Celldus Pharma Formulation & Manufacturing Unit",
                "site_type": "manufacturing",
                "address": "Plot No. 42-44, Pharma Zone, Industrial Area",
                "city": "Baddi",
                "state": "Himachal Pradesh",
                "country": "India",
                "postal_code": "173205",
                "gstin": "02AAACC1234F1Z5",
                "drug_license_no": "HP-MFG-2026-9874"
            }
        )
        self.stdout.write(f"Branch: {site}")

        # 2. Warehouses & Bins
        rm_wh, _ = Warehouse.objects.get_or_create(
            code="WH-RM-01",
            branch=site,
            defaults={
                "name": "Raw Material & API Warehouse",
                "controlled_access": True,
                "temperature_min": Decimal("20.00"),
                "temperature_max": Decimal("25.00"),
                "humidity_max": Decimal("60.00")
            }
        )
        fg_wh, _ = Warehouse.objects.get_or_create(
            code="WH-FG-01",
            branch=site,
            defaults={
                "name": "Finished Goods Central Distribution Warehouse",
                "controlled_access": False,
                "temperature_min": Decimal("15.00"),
                "temperature_max": Decimal("25.00"),
                "humidity_max": Decimal("65.00")
            }
        )

        bin_quarantine, _ = StorageBin.objects.get_or_create(
            warehouse=rm_wh,
            bin_code="BIN-Q-01",
            defaults={"zone": "Quarantine Zone", "capacity_kg": Decimal("5000.00")}
        )
        bin_released_rm, _ = StorageBin.objects.get_or_create(
            warehouse=rm_wh,
            bin_code="BIN-REL-01",
            defaults={"zone": "Released Raw Material Store", "capacity_kg": Decimal("10000.00")}
        )
        bin_fg, _ = StorageBin.objects.get_or_create(
            warehouse=fg_wh,
            bin_code="BIN-FG-A1",
            defaults={"zone": "Released Finished Goods Bay", "capacity_kg": Decimal("20000.00")}
        )

        # 3. Units of Measure
        uom_kg, _ = UnitOfMeasure.objects.get_or_create(code="KG", defaults={"name": "Kilogram", "symbol": "kg", "is_discrete": False})
        uom_gm, _ = UnitOfMeasure.objects.get_or_create(code="GM", defaults={"name": "Gram", "symbol": "g", "is_discrete": False})
        uom_mg, _ = UnitOfMeasure.objects.get_or_create(code="MG", defaults={"name": "Milligram", "symbol": "mg", "is_discrete": False})
        uom_tab, _ = UnitOfMeasure.objects.get_or_create(code="TAB", defaults={"name": "Tablet", "symbol": "Tab", "is_discrete": True})
        uom_strip, _ = UnitOfMeasure.objects.get_or_create(code="STRIP", defaults={"name": "Blister Strip (10 Tabs)", "symbol": "Strip", "is_discrete": True})
        uom_box, _ = UnitOfMeasure.objects.get_or_create(code="BOX", defaults={"name": "Outer Shipper Box", "symbol": "Box", "is_discrete": True})

        # Conversions
        UOMConversion.objects.get_or_create(from_uom=uom_kg, to_uom=uom_gm, defaults={"conversion_factor": Decimal("1000.000000")})
        UOMConversion.objects.get_or_create(from_uom=uom_gm, to_uom=uom_mg, defaults={"conversion_factor": Decimal("1000.000000")})

        # 4. User Roles Setup
        admin_user = User.objects.filter(username__in=['admin', 'superadmin']).first()
        if admin_user:
            roles = [
                'ADMIN', 'PURCHASE', 'WAREHOUSE', 'PRODUCTION', 'QC_ANALYST',
                'QA_APPROVER', 'SALES_CRM', 'ACCOUNTS', 'HR_PAYROLL', 'AUDITOR'
            ]
            for r in roles:
                ERPUserRole.objects.get_or_create(user=admin_user, role=r, branch=site)
            self.stdout.write(f"Assigned all ERP Roles to: {admin_user.username}")

        # 5. Masters: Suppliers & Customers
        supplier, _ = SupplierMaster.objects.get_or_create(
            supplier_code="SUP-001",
            defaults={
                "legal_name": "Solvents & API Synthetics Ltd.",
                "trade_name": "SolventTech APIs",
                "status": "QUALIFIED",
                "gstin": "07AAACR1234F1Z1",
                "address": "45 API Chemical Complex, Okhla",
                "city": "New Delhi",
                "state": "Delhi",
                "contact_person": "Dr. V. K. Sharma",
                "email": "supplies@solventtech.com",
                "phone": "+91 9811223344",
                "payment_terms_days": 30,
                "gmp_certificate_no": "GMP-API-2025-089"
            }
        )

        customer, _ = CustomerMaster.objects.get_or_create(
            customer_code="CUST-001",
            defaults={
                "name": "Apollo Super Specialty Hospitals Pvt Ltd",
                "customer_type": "HOSPITAL",
                "billing_address": "Sarita Vihar, Mathura Road",
                "city": "New Delhi",
                "state": "Delhi",
                "gstin": "07AAACA4567G1Z8",
                "drug_license_20b": "DL-20B-DEL-55443",
                "drug_license_21b": "DL-21B-DEL-55444",
                "contact_person": "Chief Pharmacist Rajesh Nair",
                "email": "procurement@apollohospitals.com",
                "phone": "+91 9822334455",
                "credit_limit": Decimal("5000000.00"),
                "payment_terms_days": 45
            }
        )

        # 6. Items: API, Excipient, Finished Good
        api_item, _ = ItemMaster.objects.get_or_create(
            item_code="RM-API-001",
            defaults={
                "name": "Paracetamol IP (Active Pharmaceutical Ingredient)",
                "generic_name": "Acetaminophen IP",
                "item_type": "API",
                "base_uom": uom_kg,
                "storage_condition": "ROOM_TEMP",
                "shelf_life_days": 1825,  # 5 years
                "retest_interval_days": 730,
                "reorder_min": Decimal("500.0000"),
                "reorder_max": Decimal("5000.0000"),
                "standard_cost": Decimal("450.00")
            }
        )

        excipient_item, _ = ItemMaster.objects.get_or_create(
            item_code="RM-EXC-001",
            defaults={
                "name": "Microcrystalline Cellulose IP (Avicel PH-102)",
                "generic_name": "Cellulose Microcrystalline",
                "item_type": "EXCIPIENT",
                "base_uom": uom_kg,
                "storage_condition": "ROOM_TEMP",
                "shelf_life_days": 1460,
                "reorder_min": Decimal("200.0000"),
                "reorder_max": Decimal("2000.0000"),
                "standard_cost": Decimal("180.00")
            }
        )

        fg_item, _ = ItemMaster.objects.get_or_create(
            item_code="FG-TAB-500",
            defaults={
                "name": "Celldus Paracetamol Tablets IP 500mg",
                "generic_name": "Paracetamol Tablets IP",
                "item_type": "FINISHED_GOOD",
                "dosage_form": "Tablet",
                "strength": "500mg",
                "category": "Analgesic & Antipyretic",
                "base_uom": uom_tab,
                "storage_condition": "ROOM_TEMP",
                "shelf_life_days": 1095,  # 3 years
                "reorder_min": Decimal("50000.0000"),
                "reorder_max": Decimal("500000.0000"),
                "standard_cost": Decimal("0.85"),
                "mrp": Decimal("2.50")
            }
        )

        # 7. Quality Specification for Finished Good
        spec, _ = QualitySpecification.objects.get_or_create(
            spec_code="SPEC-FG-PARA-500",
            item=fg_item,
            defaults={
                "version": 1,
                "pharmacopoeia": "IP",
                "effective_date": timezone.now().date(),
                "is_approved": True,
                "approved_by": admin_user
            }
        )

        SpecificationParameter.objects.get_or_create(
            specification=spec,
            sequence=1,
            parameter_name="Description",
            defaults={
                "test_method": "Visual Inspection",
                "acceptance_criteria": "White to off-white, round, biconvex uncoated tablets.",
                "is_critical": True
            }
        )
        SpecificationParameter.objects.get_or_create(
            specification=spec,
            sequence=2,
            parameter_name="Assay (Paracetamol)",
            defaults={
                "test_method": "HPLC IP",
                "acceptance_criteria": "Between 95.0% and 105.0% of labeled claim.",
                "min_limit": Decimal("95.0000"),
                "max_limit": Decimal("105.0000"),
                "unit": "%",
                "is_critical": True
            }
        )
        SpecificationParameter.objects.get_or_create(
            specification=spec,
            sequence=3,
            parameter_name="Dissolution (30 mins)",
            defaults={
                "test_method": "USP Apparatus II (Paddle)",
                "acceptance_criteria": "Not less than 80.0% of the labeled amount is dissolved in 30 minutes.",
                "min_limit": Decimal("80.0000"),
                "unit": "%",
                "is_critical": True
            }
        )

        # 8. BOM (Master Formula Record)
        bom, _ = BOMHeader.objects.get_or_create(
            bom_code="BOM-PARA-100K",
            product=fg_item,
            defaults={
                "version": 1,
                "batch_size": Decimal("100000.0000"),
                "batch_uom": uom_tab,
                "effective_from": timezone.now().date(),
                "status": "APPROVED",
                "approved_by": admin_user,
                "approved_at": timezone.now()
            }
        )

        BOMLine.objects.get_or_create(
            bom=bom,
            component=api_item,
            defaults={
                "quantity": Decimal("50.0000"),  # 50 kg for 100k tabs of 500mg
                "uom": uom_kg,
                "stage_name": "Dispensing & Wet Granulation"
            }
        )
        BOMLine.objects.get_or_create(
            bom=bom,
            component=excipient_item,
            defaults={
                "quantity": Decimal("15.0000"),  # 15 kg binder/excipient
                "uom": uom_kg,
                "stage_name": "Blending & Compression"
            }
        )

        # 9. Initial Seed Inventory Lots (One AVAILABLE for production/sales test, one QUARANTINE)
        today = timezone.now().date()
        lot_api_rel, _ = InventoryLot.objects.get_or_create(
            lot_number="LOT-API-2026-001",
            defaults={
                "item": api_item,
                "batch_no": "B-SOL-2601",
                "supplier": supplier,
                "warehouse": rm_wh,
                "bin": bin_released_rm,
                "manufacturing_date": today - datetime.timedelta(days=30),
                "expiry_date": today + datetime.timedelta(days=1700),
                "quantity_on_hand": Decimal("1000.0000"),
                "quantity_reserved": Decimal("0.0000"),
                "uom": uom_kg,
                "unit_cost": Decimal("450.00"),
                "status": "AVAILABLE",
                "qc_reference": "QC-COA-2026-0012",
                "released_at": timezone.now(),
                "released_by": admin_user
            }
        )

        lot_fg_rel, _ = InventoryLot.objects.get_or_create(
            lot_number="LOT-FG-2026-001",
            defaults={
                "item": fg_item,
                "batch_no": "CPT-26001",
                "warehouse": fg_wh,
                "bin": bin_fg,
                "manufacturing_date": today - datetime.timedelta(days=10),
                "expiry_date": today + datetime.timedelta(days=1085),
                "quantity_on_hand": Decimal("250000.0000"),
                "quantity_reserved": Decimal("0.0000"),
                "uom": uom_tab,
                "unit_cost": Decimal("0.85"),
                "status": "AVAILABLE",
                "qc_reference": "QC-FG-COA-26-0089",
                "released_at": timezone.now(),
                "released_by": admin_user
            }
        )

        # 10. Chart of Accounts
        ChartOfAccount.objects.get_or_create(account_code="1001", defaults={"name": "Cash on Hand", "account_type": "ASSET"})
        ChartOfAccount.objects.get_or_create(account_code="1002", defaults={"name": "HDFC Bank Corporate Current A/c", "account_type": "ASSET"})
        ChartOfAccount.objects.get_or_create(account_code="1100", defaults={"name": "Raw Materials & API Inventory", "account_type": "ASSET"})
        ChartOfAccount.objects.get_or_create(account_code="1101", defaults={"name": "Finished Goods Commercial Inventory", "account_type": "ASSET"})
        ChartOfAccount.objects.get_or_create(account_code="1200", defaults={"name": "Accounts Receivable (Debtors)", "account_type": "ASSET"})
        ChartOfAccount.objects.get_or_create(account_code="2001", defaults={"name": "Accounts Payable (Creditors)", "account_type": "LIABILITY"})
        ChartOfAccount.objects.get_or_create(account_code="4001", defaults={"name": "Pharmaceutical Domestic Sales Revenue", "account_type": "REVENUE"})
        ChartOfAccount.objects.get_or_create(account_code="5001", defaults={"name": "Cost of Goods Sold (COGS)", "account_type": "EXPENSE"})

        self.stdout.write(self.style.SUCCESS("Celldus Pharma ERP baseline successfully initialized!"))
