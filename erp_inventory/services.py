from decimal import Decimal
from django.db import transaction
from django.utils import timezone
from django.core.exceptions import ValidationError
from .models import InventoryLot, StockLedger
from erp_core.security import audit_log_event


def get_fefo_allocations(item_id, required_qty: Decimal, warehouse_id=None):
    """
    Core FEFO (First-Expired, First-Out) Engine:
    Finds all eligible lots (AVAILABLE, unexpired, non-zero quantity) sorted by expiry_date ASC.
    Calculates exact lot-level allocation quantities.
    """
    today = timezone.now().date()
    qs = InventoryLot.objects.filter(
        item_id=item_id,
        status='AVAILABLE',
        expiry_date__gte=today,
        quantity_on_hand__gt=Decimal('0.0000')
    ).order_by('expiry_date', 'created_at')

    if warehouse_id:
        qs = qs.filter(warehouse_id=warehouse_id)

    allocations = []
    remaining_needed = Decimal(str(required_qty))

    for lot in qs:
        avail = lot.quantity_available
        if avail <= Decimal('0.0000'):
            continue

        take = min(avail, remaining_needed)
        allocations.append({
            'lot_id': lot.id,
            'lot_number': lot.lot_number,
            'batch_no': lot.batch_no,
            'expiry_date': lot.expiry_date.isoformat(),
            'warehouse_id': lot.warehouse_id,
            'bin_id': lot.bin_id,
            'allocated_qty': take,
            'uom_code': lot.uom.code,
            'unit_cost': lot.unit_cost
        })

        remaining_needed -= take
        if remaining_needed <= Decimal('0.0000'):
            break

    return {
        'is_fulfillable': remaining_needed <= Decimal('0.0000'),
        'required_qty': required_qty,
        'allocated_total': required_qty - max(Decimal('0.0000'), remaining_needed),
        'shortage_qty': max(Decimal('0.0000'), remaining_needed),
        'allocations': allocations
    }


@transaction.atomic
def reserve_stock_fefo(item_id, required_qty: Decimal, document_no: str, user, warehouse_id=None):
    """
    Reserves stock using FEFO and atomically increments quantity_reserved on matching lots.
    """
    fefo_res = get_fefo_allocations(item_id, required_qty, warehouse_id)
    if not fefo_res['is_fulfillable']:
        raise ValidationError(f"Insufficient unreserved, released stock for item. Shortage: {fefo_res['shortage_qty']}")

    reserved_lots = []
    for alloc in fefo_res['allocations']:
        lot = InventoryLot.objects.select_for_update().get(id=alloc['lot_id'])
        lot.quantity_reserved += alloc['allocated_qty']
        lot.save(update_fields=['quantity_reserved', 'updated_at'])
        reserved_lots.append(lot)

        audit_log_event(
            user=user,
            action='UPDATE',
            entity_name='InventoryLot',
            entity_id=lot.id,
            document_no=document_no,
            reason=f"FEFO reserved {alloc['allocated_qty']} for document {document_no}"
        )

    return fefo_res
