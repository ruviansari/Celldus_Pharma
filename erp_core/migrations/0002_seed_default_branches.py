from django.db import migrations

DEFAULT_BRANCHES = [
    {
        "code": "SITE-01",
        "name": "Celldus Pharma Formulation & Manufacturing Unit",
        "site_type": "manufacturing",
        "address": "Plot No. 42-44, Pharma Zone, Industrial Area",
        "city": "Baddi",
        "state": "Himachal Pradesh",
        "country": "India",
        "postal_code": "173205",
        "gstin": "02AAACC1234F1Z5",
        "drug_license_no": "HP-MFG-2026-9874",
        "is_active": True,
    },
    {
        "code": "RND-BLR",
        "name": "Celldus Formulation R&D & Analytical Testing Center",
        "site_type": "rnd",
        "address": "Tech Park Phase 2, Whitefield",
        "city": "Bangalore",
        "state": "Karnataka",
        "country": "India",
        "postal_code": "560066",
        "gstin": "29AAACC1234F1Z1",
        "drug_license_no": "KA-RND-2026-1102",
        "is_active": True,
    },
    {
        "code": "WH-MUMBAI",
        "name": "Western Regional Distribution Center & Central Warehouse",
        "site_type": "warehouse",
        "address": "Warehouse Hub 12, Logistic Park, Bhiwandi",
        "city": "Mumbai",
        "state": "Maharashtra",
        "country": "India",
        "postal_code": "421302",
        "gstin": "27AAACC1234F1Z3",
        "drug_license_no": "MH-WH-2026-4412",
        "is_active": True,
    },
]


def seed_branches(apps, schema_editor):
    Branch = apps.get_model('erp_core', 'Branch')
    for branch_data in DEFAULT_BRANCHES:
        code = branch_data["code"]
        Branch.objects.get_or_create(code=code, defaults=branch_data)


def unseed_branches(apps, schema_editor):
    # Reverse migration - keep records or no-op to preserve data safety
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('erp_core', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(seed_branches, reverse_code=unseed_branches),
    ]
