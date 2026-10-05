from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from decimal import Decimal
from django.utils import timezone
from .models import InventoryLot, StockLedger, CycleCountSession, CycleCountLine
from .serializers import (
    InventoryLotSerializer, StockLedgerSerializer,
    CycleCountSessionSerializer, CycleCountLineSerializer
)
from .services import get_fefo_allocations
from erp_core.security import audit_log_event, check_prevent_self_approval


class InventoryLotViewSet(viewsets.ModelViewSet):
    """
    CRUD and actions on Inventory Lots.
    Supports filtering by item, batch_no, warehouse, status.
    """
    queryset = InventoryLot.objects.select_related('item', 'warehouse', 'bin', 'uom').all()
    serializer_class = InventoryLotSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        qs = super().get_queryset()
        status_param = self.request.query_params.get('status')
        item_id = self.request.query_params.get('item')
        warehouse_id = self.request.query_params.get('warehouse')
        search = self.request.query_params.get('search')

        if status_param:
            qs = qs.filter(status=status_param)
        if item_id:
            qs = qs.filter(item_id=item_id)
        if warehouse_id:
            qs = qs.filter(warehouse_id=warehouse_id)
        if search:
            qs = qs.filter(lot_number__icontains=search) | qs.filter(batch_no__icontains=search) | qs.filter(item__name__icontains=search)

        return qs

    @action(detail=False, methods=['get'])
    def fefo_quote(self, request):
        """
        Calculates FEFO lot allocation for an item and quantity without modifying state.
        Query params: ?item_id=...&qty=...&warehouse_id=...
        """
        item_id = request.query_params.get('item_id')
        qty = request.query_params.get('qty')
        warehouse_id = request.query_params.get('warehouse_id')

        if not item_id or not qty:
            return Response({'error': 'item_id and qty are required.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            qty_decimal = Decimal(str(qty))
        except Exception:
            return Response({'error': 'Invalid quantity.'}, status=status.HTTP_400_BAD_REQUEST)

        res = get_fefo_allocations(item_id, qty_decimal, warehouse_id)
        return Response(res)

    @action(detail=True, methods=['post'])
    def block_lot(self, request, pk=None):
        lot = self.get_object()
        reason = request.data.get('reason')
        if not reason:
            return Response({'error': 'A valid reason is required to block an inventory lot.'}, status=status.HTTP_400_BAD_REQUEST)

        lot.status = 'BLOCKED'
        lot.save(update_fields=['status', 'updated_at'])

        audit_log_event(
            user=request.user,
            action='UPDATE',
            entity_name='InventoryLot',
            entity_id=lot.id,
            document_no=lot.lot_number,
            reason=f"Lot blocked: {reason}",
            request=request
        )
        return Response({'status': 'Blocked', 'lot_number': lot.lot_number})


class StockLedgerReadOnlyViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Permanent, immutable stock movement audit ledger.
    """
    queryset = StockLedger.objects.select_related('lot', 'item', 'uom', 'user', 'from_warehouse', 'to_warehouse').all()
    serializer_class = StockLedgerSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        qs = super().get_queryset()
        item_id = self.request.query_params.get('item')
        doc_no = self.request.query_params.get('doc_no')
        tx_type = self.request.query_params.get('type')

        if item_id:
            qs = qs.filter(item_id=item_id)
        if doc_no:
            qs = qs.filter(document_no__icontains=doc_no)
        if tx_type:
            qs = qs.filter(transaction_type=tx_type)

        return qs


class CycleCountSessionViewSet(viewsets.ModelViewSet):
    queryset = CycleCountSession.objects.select_related('warehouse').prefetch_related('lines__item', 'lines__lot').all()
    serializer_class = CycleCountSessionSerializer
    permission_classes = [permissions.IsAuthenticated]
