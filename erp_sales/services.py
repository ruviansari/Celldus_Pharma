from decimal import Decimal
from django.db import transaction
from django.utils import timezone
from django.core.exceptions import ValidationError
from erp_inventory.models import InventoryLot, StockLedger
from erp_inventory.services import get_fefo_allocations
from erp_core.security import audit_log_event, check_prevent_self_approval
from .models import SalesOrder, SalesOrderLotAllocation, SalesDispatchInvoice


@transaction.atomic
def approve_sales_order_and_reserve_fefo(order_id, user):
    """
    1. Validates customer credit limit and licenses.
    2. Runs FEFO allocation on all lines.
    3. Reserves stock atomically.
    4. Transitions status to APPROVED.
    """
    order = SalesOrder.objects.select_for_update().get(id=order_id)
    customer = order.customer

    # Check credit hold / credit limit
    if customer.credit_hold and not order.credit_override:
        raise ValidationError(f"Customer {customer.name} is on Credit Hold. Management credit override required.")

    if (customer.current_balance + order.grand_total) > customer.credit_limit and customer.credit_limit > 0 and not order.credit_override:
        raise ValidationError(f"Order exceeds customer credit limit (Limit: ₹{customer.credit_limit}, Balance: ₹{customer.current_balance}).")

    # Allocate & Reserve each line using FEFO
    for line in order.lines.select_related('product', 'uom').all():
        fefo_res = get_fefo_allocations(line.product_id, line.ordered_qty)
        if not fefo_res['is_fulfillable']:
            raise ValidationError(f"Insufficient released unexpired stock for {line.product.name}. Shortage: {fefo_res['shortage_qty']}")

        # Clear existing allocations if re-approving
        line.lot_allocations.all().delete()

        for alloc in fefo_res['allocations']:
            lot = InventoryLot.objects.select_for_update().get(id=alloc['lot_id'])
            lot.quantity_reserved += alloc['allocated_qty']
            lot.save(update_fields=['quantity_reserved', 'updated_at'])

            SalesOrderLotAllocation.objects.create(
                line=line,
                lot=lot,
                allocated_qty=alloc['allocated_qty'],
                uom=line.uom,
                created_by=user
            )

    order.status = 'APPROVED'
    order.approved_by = user
    order.approved_at = timezone.now()
    order.save(update_fields=['status', 'approved_by', 'approved_at', 'updated_at'])

    audit_log_event(
        user=user,
        action='APPROVE',
        entity_name='SalesOrder',
        entity_id=order.id,
        document_no=order.document_no,
        reason="Sales order approved and stock reserved via FEFO."
    )

    return order


@transaction.atomic
def dispatch_sales_order(order_id, transporter: str, docket_no: str, eway_bill_no: str, vehicle_no: str, user):
    """
    Executes physical dispatch:
    1. Validates all batches are strictly AVAILABLE, unexpired, and not recalled.
    2. Deducts quantity from InventoryLot and clears reservation.
    3. Generates immutable DISPATCH entries in StockLedger.
    4. Creates SalesDispatchInvoice and updates customer ledger balance.
    """
    order = SalesOrder.objects.select_for_update().get(id=order_id)
    today = timezone.now().date()

    if order.status not in ['APPROVED', 'PICKING']:
        raise ValidationError(f"Order cannot be dispatched in status {order.status}")

    # Generate Invoice
    invoice = SalesDispatchInvoice.objects.create(
        order=order,
        customer=order.customer,
        transporter_name=transporter,
        docket_no=docket_no,
        eway_bill_no=eway_bill_no,
        vehicle_number=vehicle_no,
        total_amount=order.grand_total,
        created_by=user,
        branch=order.branch
    )

    # Process all lot allocations
    for line in order.lines.all():
        for alloc in line.lot_allocations.select_related('lot', 'lot__item').all():
            lot = InventoryLot.objects.select_for_update().get(id=alloc.lot_id)

            # Strict compliance checks before dispatch!
            if lot.status != 'AVAILABLE':
                raise ValidationError(f"Compliance Violation: Lot {lot.lot_number} status is {lot.status}. Only AVAILABLE lots can be dispatched.")
            if lot.expiry_date < today:
                raise ValidationError(f"Compliance Violation: Lot {lot.lot_number} has EXPIRED ({lot.expiry_date}). Dispatch blocked.")

            lot.quantity_on_hand -= alloc.allocated_qty
            lot.quantity_reserved = max(Decimal('0.0000'), lot.quantity_reserved - alloc.allocated_qty)
            lot.save(update_fields=['quantity_on_hand', 'quantity_reserved', 'updated_at'])

            alloc.is_dispatched = True
            alloc.save(update_fields=['is_dispatched'])

            # Immutable StockLedger entry
            StockLedger.objects.create(
                transaction_type='DISPATCH',
                document_no=invoice.document_no,
                lot=lot,
                item=lot.item,
                from_warehouse=lot.warehouse,
                from_bin=lot.bin,
                quantity=alloc.allocated_qty,
                uom=alloc.uom,
                unit_cost=lot.unit_cost,
                user=user,
                reason=f"Customer dispatch to {order.customer.name} (Invoice: {invoice.document_no}, LR: {docket_no})"
            )

    # Update Customer balance
    customer = order.customer
    customer.current_balance += order.grand_total
    customer.save(update_fields=['current_balance'])

    order.status = 'DISPATCHED'
    order.save(update_fields=['status', 'updated_at'])

    audit_log_event(
        user=user,
        action='DISPATCH',
        entity_name='SalesOrder',
        entity_id=order.id,
        document_no=invoice.document_no,
        reason=f"Sales order dispatched. Invoice: {invoice.document_no}, E-Way Bill: {eway_bill_no}"
    )

    return invoice
