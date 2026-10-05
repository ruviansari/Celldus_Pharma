import re
from django.db import transaction
from django.utils import timezone
from .models import Lead, LeadImportBatch
from erp_core.models import DocumentSequence
from erp_core.security import audit_log_event


def normalize_phone(phone_str: str) -> str:
    """Normalizes phone string to standard 10-digit format."""
    digits = re.sub(r'\D', '', str(phone_str or ''))
    if digits.startswith('91') and len(digits) == 12:
        digits = digits[2:]
    return digits[-10:] if len(digits) >= 10 else digits


def normalize_email(email_str: str) -> str:
    return str(email_str or '').strip().lower()


def process_lead_import_rows(rows_data: list, file_name: str, user, commit: bool = False):
    """
    Validates, normalizes, detects duplicates, and imports leads from CSV / Excel rows.
    """
    batch_no = DocumentSequence.get_next_number('IMPORT')

    valid_leads = []
    duplicate_leads = []
    error_leads = []

    for index, row in enumerate(rows_data, start=1):
        org = row.get('organization_name', '').strip()
        contact = row.get('contact_person', '').strip()
        phone = normalize_phone(row.get('phone', ''))
        email = normalize_email(row.get('email', ''))

        if not org or not contact:
            error_leads.append({'row': index, 'reason': 'Missing Organization Name or Contact Person'})
            continue

        if not phone and not email:
            error_leads.append({'row': index, 'reason': 'At least one phone number or email is mandatory'})
            continue

        # Check Duplicate
        existing = Lead.objects.filter(phone=phone).first() if phone else None
        if not existing and email:
            existing = Lead.objects.filter(email=email).first()

        if existing:
            duplicate_leads.append({
                'row': index,
                'organization': org,
                'phone': phone,
                'email': email,
                'existing_lead_id': existing.lead_id,
                'existing_stage': existing.stage
            })
            continue

        valid_leads.append({
            'row': index,
            'organization_name': org,
            'contact_person': contact,
            'phone': phone,
            'email': email,
            'city': row.get('city', ''),
            'state': row.get('state', ''),
            'territory': row.get('territory', ''),
            'lead_type': row.get('lead_type', 'DISTRIBUTOR'),
            'source': row.get('source', 'Bulk Import')
        })

    import_batch = LeadImportBatch.objects.create(
        batch_no=batch_no,
        file_name=file_name,
        total_rows=len(rows_data),
        valid_rows=len(valid_leads),
        duplicate_rows=len(duplicate_leads),
        error_rows=len(error_leads),
        import_summary={
            'duplicates': duplicate_leads[:50],
            'errors': error_leads[:50]
        },
        is_confirmed=commit,
        created_by=user
    )

    if commit:
        with transaction.atomic():
            for v in valid_leads:
                Lead.objects.create(
                    organization_name=v['organization_name'],
                    contact_person=v['contact_person'],
                    phone=v['phone'],
                    email=v['email'],
                    city=v['city'],
                    state=v['state'],
                    territory=v['territory'],
                    lead_type=v['lead_type'],
                    source=v['source'],
                    stage='NEW',
                    created_by=user
                )

        audit_log_event(
            user=user,
            action='CREATE',
            entity_name='LeadImportBatch',
            entity_id=import_batch.id,
            document_no=batch_no,
            reason=f"Committed {len(valid_leads)} leads from file {file_name}"
        )

    return {
        'batch_no': batch_no,
        'total': len(rows_data),
        'valid_count': len(valid_leads),
        'duplicate_count': len(duplicate_leads),
        'error_count': len(error_leads),
        'preview_valid': valid_leads[:10],
        'preview_duplicates': duplicate_leads[:10],
        'preview_errors': error_leads[:10],
        'is_committed': commit
    }
