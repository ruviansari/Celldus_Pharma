from decimal import Decimal
from django.db import transaction
from django.utils import timezone
from django.core.exceptions import ValidationError
from erp_inventory.models import InventoryLot, StockLedger
from erp_quality.models import QCInspectionRequest
from erp_masters.models import QualitySpecification
from erp_core.models import DocumentSequence
from erp_core.security import audit_log_event
from .models import ProductionOrder


@transaction.atomic
def complete_production_batch(order_id, actual_qty: Decimal, scrap_qty: Decimal, user):
    """
    Executes production batch completion:
    1. Deducts consumed raw materials from inventory.
    2. Creates new Finished Goods lot in QUARANTINE status.
    3. Triggers QC Inspection Request automatically.
    4. Calculates yield percentage.
    """
    order = ProductionOrder.objects.select_for_update().get(id=order_id)

    if order.status not in ['RELEASED', 'IN_PROGRESS']:
        raise ValidationError(f"Cannot complete order in status {order.status}")

    order.actual_produced_qty = actual_qty
    order.scrap_qty = scrap_qty
    order.actual_end_time = timezone.now()

    # Calculate Yield %
    if order.planned_qty > 0:
        order.yield_percentage = (actual_qty / order.planned_qty) * Decimal('100.00')

    # 1. Deduct consumed materials from inventory
    for cons in order.material_consumptions.select_related('lot', 'component', 'uom').all():
        lot = InventoryLot.objects.select_for_update().get(id=cons.lot_id)
        if lot.quantity_on_hand < cons.actual_consumed_qty:
            raise ValidationError(f"Insufficient stock on lot {lot.lot_number} to record consumption.")

        lot.quantity_on_hand -= cons.actual_consumed_qty
        lot.quantity_reserved = max(Decimal('0.0000'), lot.quantity_reserved - cons.actual_consumed_qty)
        lot.save(update_fields=['quantity_on_hand', 'quantity_reserved', 'updated_at'])

        StockLedger.objects.create(
            transaction_type='MATERIAL_ISSUE',
            document_no=order.document_no,
            lot=lot,
            item=cons.component,
            from_warehouse=lot.warehouse,
            from_bin=lot.bin,
            quantity=cons.actual_consumed_qty,
            uom=cons.uom,
            unit_cost=lot.unit_cost,
            user=user,
            reason=f"Dispensed & consumed in Batch {order.batch_no} (Order: {order.document_no})"
        )

    # 2. Create Finished Goods Lot in QUARANTINE status
    finished_lot_no = DocumentSequence.get_next_number('FG-LOT', order.branch)
    fg_lot = InventoryLot.objects.create(
        lot_number=finished_lot_no,
        item=order.product,
        batch_no=order.batch_no,
        warehouse=order.target_warehouse,
        bin=order.target_bin,
        manufacturing_date=order.manufacturing_date,
        expiry_date=order.expiry_date,
        quantity_on_hand=actual_qty,
        quantity_reserved=Decimal('0.0000'),
        uom=order.uom,
        unit_cost=order.product.standard_cost,
        status='QUARANTINE',  # Strictly Quarantined until QA disposition!
        created_by=user
    )

    order.finished_lot = fg_lot
    order.status = 'COMPLETED'
    order.save(update_fields=['actual_produced_qty', 'scrap_qty', 'actual_end_time', 'yield_percentage', 'finished_lot', 'status', 'updated_at'])

    # 3. Post Production Receipt to Stock Ledger
    StockLedger.objects.create(
        transaction_type='PRODUCTION_RECEIPT',
        document_no=order.document_no,
        lot=fg_lot,
        item=order.product,
        to_warehouse=order.target_warehouse,
        to_bin=order.target_bin,
        quantity=actual_qty,
        uom=order.uom,
        unit_cost=order.product.standard_cost,
        user=user,
        reason=f"Finished batch {order.batch_no} receipt. Quarantined awaiting QC."
    )

    # 4. Automatically trigger QC Inspection Request if a quality spec exists
    spec = QualitySpecification.objects.filter(item=order.product, is_approved=True).order_by('-version').first()
    if spec:
        QCInspectionRequest.objects.create(
            lot=fg_lot,
            item=order.product,
            specification=spec,
            status='PENDING_SAMPLING',
            created_by=user,
            branch=order.branch
        )

    audit_log_event(
        user=user,
        action='POST',
        entity_name='ProductionOrder',
        entity_id=order.id,
        document_no=order.document_no,
        reason=f"Batch {order.batch_no} completed ({actual_qty} {order.uom.code}). Finished lot {finished_lot_no} created in QUARANTINE."
    )

    return order
