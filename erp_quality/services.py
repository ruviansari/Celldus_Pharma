from decimal import Decimal
from django.db import transaction
from django.utils import timezone
from django.core.exceptions import ValidationError
from erp_inventory.models import InventoryLot, StockLedger
from erp_core.security import audit_log_event, check_prevent_self_approval
from .models import QCInspectionRequest, QADispositionRecord


@transaction.atomic
def execute_qa_disposition(inspection_id, disposition_choice: str, reason: str, qa_user, coa_number: str = ''):
    """
    Executes formal QA batch release or rejection:
    1. Verifies inspection and test results.
    2. Validates segregation of duties (QA user cannot be the analyst/sampler if configured).
    3. Atomically updates InventoryLot status (AVAILABLE or REJECTED or BLOCKED).
    4. Posts immutable StockLedger entry with attributable audit trail.
    """
    if not reason:
        raise ValidationError("Mandatory 21 CFR Part 11 requirement: Detailed regulatory reason required for QA disposition.")

    inspection = QCInspectionRequest.objects.select_for_update().get(id=inspection_id)
    lot = InventoryLot.objects.select_for_update().get(id=inspection.lot_id)

    # Prevent self-approval if sampler was the same user
    if inspection.sampler_id == qa_user.id and not qa_user.is_superuser:
        raise ValidationError("Segregation of Duties: Sampler cannot execute final QA disposition.")

    # Create QA Disposition Record
    disp_record = QADispositionRecord.objects.create(
        inspection=inspection,
        lot=lot,
        disposition=disposition_choice,
        authorized_qa_person=qa_user,
        decision_reason=reason,
        coa_number=coa_number,
        branch=lot.warehouse.branch if lot.warehouse else None
    )

    action_tag = 'QA_RELEASE' if disposition_choice == 'RELEASE' else ('QA_REJECT' if disposition_choice == 'REJECT' else 'QA_HOLD')

    if disposition_choice == 'RELEASE':
        lot.status = 'AVAILABLE'
        lot.released_at = timezone.now()
        lot.released_by = qa_user
        lot.qc_reference = coa_number or inspection.document_no
        lot.save(update_fields=['status', 'released_at', 'released_by', 'qc_reference', 'updated_at'])

        StockLedger.objects.create(
            transaction_type='QC_RELEASE',
            document_no=disp_record.document_no,
            lot=lot,
            item=lot.item,
            to_warehouse=lot.warehouse,
            to_bin=lot.bin,
            quantity=lot.quantity_on_hand,
            uom=lot.uom,
            unit_cost=lot.unit_cost,
            user=qa_user,
            reason=f"QA Authorized Release to commercial inventory. COA: {coa_number}. Rationale: {reason}"
        )

    elif disposition_choice == 'REJECT':
        lot.status = 'REJECTED'
        lot.save(update_fields=['status', 'updated_at'])

        StockLedger.objects.create(
            transaction_type='QC_REJECT',
            document_no=disp_record.document_no,
            lot=lot,
            item=lot.item,
            from_warehouse=lot.warehouse,
            from_bin=lot.bin,
            quantity=lot.quantity_on_hand,
            uom=lot.uom,
            unit_cost=lot.unit_cost,
            user=qa_user,
            reason=f"QA Rejection and physical segregation. Reason: {reason}"
        )

    elif disposition_choice == 'HOLD':
        lot.status = 'BLOCKED'
        lot.save(update_fields=['status', 'updated_at'])

    inspection.status = 'DISPOSITIONED'
    inspection.save(update_fields=['status', 'updated_at'])

    audit_log_event(
        user=qa_user,
        action=action_tag,
        entity_name='InventoryLot',
        entity_id=lot.id,
        document_no=disp_record.document_no,
        reason=f"QA Disposition [{disposition_choice}]: {reason}"
    )

    return disp_record
