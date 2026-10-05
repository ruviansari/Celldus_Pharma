from decimal import Decimal
from django.db import transaction
from django.utils import timezone
from django.core.exceptions import ValidationError
from erp_inventory.models import InventoryLot, StockLedger
from erp_core.models import DocumentSequence
from erp_core.security import audit_log_event
from .models import GoodsReceiptNote, GoodsReceiptNoteLine


@transaction.atomic
def post_grn_receipt(grn_id, user):
    """
    Posts GRN into inventory:
    - Creates Quarantine Lot for each line
    - Generates immutable StockLedger entry
    - Updates PO line received quantities
    - Preserves attributable audit history
    """
    grn = GoodsReceiptNote.objects.select_for_update().get(id=grn_id)

    if grn.status != 'QUARANTINED':
        raise ValidationError("GRN is already processed.")

    created_lots = []

    for line in grn.lines.select_related('item', 'uom', 'po_line').all():
        # Generate internal unique lot number
        internal_lot_no = DocumentSequence.get_next_number('LOT', grn.branch)

        # Create Quarantine Lot
        lot = InventoryLot.objects.create(
            lot_number=internal_lot_no,
            item=line.item,
            batch_no=line.supplier_batch_no,
            supplier_lot_no=line.supplier_batch_no,
            supplier=grn.supplier,
            warehouse=grn.warehouse,
            bin=line.bin,
            manufacturing_date=line.manufacturing_date,
            expiry_date=line.expiry_date,
            quantity_on_hand=line.received_qty,
            quantity_reserved=Decimal('0.0000'),
            uom=line.uom,
            unit_cost=line.po_line.rate,
            status='QUARANTINE',
            created_by=user
        )

        line.lot = lot
        line.save(update_fields=['lot'])
        created_lots.append(lot)

        # Post immutable StockLedger entry
        StockLedger.objects.create(
            transaction_type='GRN_RECEIPT',
            document_no=grn.document_no,
            lot=lot,
            item=line.item,
            to_warehouse=grn.warehouse,
            to_bin=line.bin,
            quantity=line.received_qty,
            uom=line.uom,
            unit_cost=line.po_line.rate,
            user=user,
            reason=f"GRN Receipt against PO {grn.po.document_no}, placed in quarantine."
        )

        # Update PO Line
        po_line = line.po_line
        po_line.received_qty += line.received_qty
        po_line.save(update_fields=['received_qty'])

    # Update PO status
    po = grn.po
    all_lines = po.lines.all()
    if all(l.received_qty >= l.ordered_qty for l in all_lines):
        po.status = 'COMPLETED'
    else:
        po.status = 'PARTIALLY_RECEIVED'
    po.save(update_fields=['status'])

    audit_log_event(
        user=user,
        action='POST',
        entity_name='GoodsReceiptNote',
        entity_id=grn.id,
        document_no=grn.document_no,
        reason=f"GRN posted to quarantine with {len(created_lots)} lots."
    )

    return grn
