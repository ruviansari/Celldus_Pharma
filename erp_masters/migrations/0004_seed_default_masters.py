from decimal import Decimal
from django.db import migrations

UOM_DEFINITIONS = [
    {"code": "KG", "name": "Kilogram", "symbol": "kg", "is_discrete": False},
    {"code": "GM", "name": "Gram", "symbol": "g", "is_discrete": False},
    {"code": "MG", "name": "Milligram", "symbol": "mg", "is_discrete": False},
    {"code": "TAB", "name": "Tablet", "symbol": "Tab", "is_discrete": True},
    {"code": "STRIP", "name": "Blister Strip (10 Tabs)", "symbol": "Strip", "is_discrete": True},
    {"code": "BOX", "name": "Outer Shipper Box", "symbol": "Box", "is_discrete": True},
    {"code": "ML", "name": "Millilitre", "symbol": "ml", "is_discrete": False},
    {"code": "LTR", "name": "Litre", "symbol": "L", "is_discrete": False},
    {"code": "CAP", "name": "Capsule", "symbol": "Cap", "is_discrete": True},
    {"code": "VIAL", "name": "Vial", "symbol": "Vial", "is_discrete": True},
    {"code": "AMP", "name": "Ampoule", "symbol": "Amp", "is_discrete": True},
]

def seed_masters(apps, schema_editor):
    UnitOfMeasure = apps.get_model('erp_masters', 'UnitOfMeasure')
    UOMConversion = apps.get_model('erp_masters', 'UOMConversion')
    ItemMaster = apps.get_model('erp_masters', 'ItemMaster')
    SupplierMaster = apps.get_model('erp_masters', 'SupplierMaster')
    CustomerMaster = apps.get_model('erp_masters', 'CustomerMaster')
    Warehouse = apps.get_model('erp_masters', 'Warehouse')
    Branch = apps.get_model('erp_core', 'Branch')

    # 1. Seed Units of Measure
    uom_map = {}
    for item in UOM_DEFINITIONS:
        obj, _ = UnitOfMeasure.objects.get_or_create(
            code=item["code"],
            defaults={
                "name": item["name"],
                "symbol": item["symbol"],
                "is_discrete": item["is_discrete"],
            }
        )
        uom_map[item["code"]] = obj

    # 2. Seed UOM conversions
    if "KG" in uom_map and "GM" in uom_map:
        UOMConversion.objects.get_or_create(
            from_uom=uom_map["KG"],
            to_uom=uom_map["GM"],
            defaults={"conversion_factor": Decimal("1000.000000")}
        )
    if "GM" in uom_map and "MG" in uom_map:
        UOMConversion.objects.get_or_create(
            from_uom=uom_map["GM"],
            to_uom=uom_map["MG"],
            defaults={"conversion_factor": Decimal("1000.000000")}
        )

    # 3. Seed Suppliers
    SupplierMaster.objects.get_or_create(
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

    # 4. Seed Customers
    CustomerMaster.objects.get_or_create(
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

    # 5. Seed Items (APIs, Excipients, Finished Goods)
    if "KG" in uom_map:
        ItemMaster.objects.get_or_create(
            item_code="RM-API-001",
            defaults={
                "name": "Paracetamol IP (Active Pharmaceutical Ingredient)",
                "generic_name": "Acetaminophen IP",
                "item_type": "API",
                "base_uom": uom_map["KG"],
                "storage_condition": "ROOM_TEMP",
                "shelf_life_days": 1825,
                "retest_interval_days": 730,
                "reorder_min": Decimal("500.0000"),
                "reorder_max": Decimal("5000.0000"),
                "standard_cost": Decimal("450.00"),
                "tax_rate": Decimal("12.00"),
            }
        )
        ItemMaster.objects.get_or_create(
            item_code="RM-EXC-001",
            defaults={
                "name": "Microcrystalline Cellulose IP (Avicel PH-102)",
                "generic_name": "Cellulose Microcrystalline",
                "item_type": "EXCIPIENT",
                "base_uom": uom_map["KG"],
                "storage_condition": "ROOM_TEMP",
                "shelf_life_days": 1460,
                "reorder_min": Decimal("200.0000"),
                "reorder_max": Decimal("2000.0000"),
                "standard_cost": Decimal("180.00"),
                "tax_rate": Decimal("12.00"),
            }
        )
        ItemMaster.objects.get_or_create(
            item_code="RM-API-AMOX",
            defaults={
                "name": "Amoxicillin Trihydrate IP (Micronized Grade)",
                "generic_name": "Amoxicillin Trihydrate IP",
                "item_type": "API",
                "base_uom": uom_map["KG"],
                "storage_condition": "ROOM_TEMP",
                "shelf_life_days": 1095,
                "reorder_min": Decimal("100.0000"),
                "reorder_max": Decimal("1000.0000"),
                "standard_cost": Decimal("1850.00"),
                "tax_rate": Decimal("12.00"),
            }
        )

    if "TAB" in uom_map:
        ItemMaster.objects.get_or_create(
            item_code="FG-TAB-500",
            defaults={
                "name": "Celldus Paracetamol Tablets IP 500mg",
                "generic_name": "Paracetamol Tablets IP",
                "item_type": "FINISHED_GOOD",
                "dosage_form": "Tablet",
                "strength": "500mg",
                "category": "Analgesic & Antipyretic",
                "base_uom": uom_map["TAB"],
                "storage_condition": "ROOM_TEMP",
                "shelf_life_days": 1095,
                "reorder_min": Decimal("50000.0000"),
                "reorder_max": Decimal("500000.0000"),
                "standard_cost": Decimal("0.85"),
                "mrp": Decimal("2.50"),
                "tax_rate": Decimal("12.00"),
            }
        )
        ItemMaster.objects.get_or_create(
            item_code="FG-AMOX-625",
            defaults={
                "name": "Amoxicillin & Potassium Clavulanate Tablets IP 625mg",
                "generic_name": "Amoxicillin Clavulanate IP",
                "item_type": "FINISHED_GOOD",
                "dosage_form": "Tablet",
                "strength": "625mg",
                "category": "Antibiotic",
                "base_uom": uom_map["TAB"],
                "storage_condition": "ROOM_TEMP",
                "shelf_life_days": 730,
                "reorder_min": Decimal("10000.0000"),
                "reorder_max": Decimal("100000.0000"),
                "standard_cost": Decimal("4.50"),
                "mrp": Decimal("12.00"),
                "tax_rate": Decimal("12.00"),
            }
        )

    # 6. Seed Warehouses if site branch exists
    site_branch = Branch.objects.filter(code="SITE-01").first()
    if not site_branch:
        site_branch = Branch.objects.first()

    if site_branch:
        Warehouse.objects.get_or_create(
            code="WH-RM-01",
            branch=site_branch,
            defaults={
                "name": "Raw Material & API Warehouse",
                "warehouse_type": "RAW_MATERIALS",
                "controlled_access": True,
                "temperature_min": Decimal("20.00"),
                "temperature_max": Decimal("25.00"),
                "humidity_max": Decimal("60.00"),
            }
        )
        Warehouse.objects.get_or_create(
            code="WH-FG-01",
            branch=site_branch,
            defaults={
                "name": "Finished Goods Central Distribution Warehouse",
                "warehouse_type": "FINISHED_GOODS",
                "controlled_access": False,
                "temperature_min": Decimal("15.00"),
                "temperature_max": Decimal("25.00"),
                "humidity_max": Decimal("65.00"),
            }
        )


def unseed_masters(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('erp_core', '0002_seed_default_branches'),
        ('erp_masters', '0003_alter_customermaster_options_and_more'),
    ]

    operations = [
        migrations.RunPython(seed_masters, reverse_code=unseed_masters),
    ]
