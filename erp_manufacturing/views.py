from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from decimal import Decimal
from django.utils import timezone
from .models import ProductionOrder, BatchMaterialConsumption, BatchProcessStep
from .serializers import ProductionOrderSerializer, BatchMaterialConsumptionSerializer, BatchProcessStepSerializer
from .services import complete_production_batch
from erp_core.security import audit_log_event


class ProductionOrderViewSet(viewsets.ModelViewSet):
    queryset = ProductionOrder.objects.select_related('product', 'bom', 'uom', 'target_warehouse', 'finished_lot').prefetch_related('material_consumptions', 'process_steps').all()
    serializer_class = ProductionOrderSerializer
    permission_classes = [permissions.IsAuthenticated]

    def perform_create(self, serializer):
        order = serializer.save(created_by=self.request.user)
        audit_log_event(self.request.user, 'CREATE', 'ProductionOrder', order.id, order.document_no, request=self.request)

    @action(detail=True, methods=['post'])
    def release_order(self, request, pk=None):
        order = self.get_object()
        order.status = 'RELEASED'
        order.actual_start_time = timezone.now()
        order.save(update_fields=['status', 'actual_start_time', 'updated_at'])

        audit_log_event(request.user, 'UPDATE', 'ProductionOrder', order.id, order.document_no, reason="Supervisor released BMR for manufacturing", request=request)
        return Response({'status': 'Released', 'document_no': order.document_no})

    @action(detail=True, methods=['post'])
    def complete(self, request, pk=None):
        """
        Completes batch execution, consumes materials, creates finished lot in QUARANTINE, and triggers QC.
        Body: {"actual_qty": 50000, "scrap_qty": 200}
        """
        actual_qty = request.data.get('actual_qty')
        scrap_qty = request.data.get('scrap_qty', 0)

        if not actual_qty:
            return Response({'error': 'actual_qty is required.'}, status=status.HTTP_400_BAD_REQUEST)

        order = complete_production_batch(pk, Decimal(str(actual_qty)), Decimal(str(scrap_qty)), request.user)
        return Response({
            'status': 'Completed',
            'document_no': order.document_no,
            'batch_no': order.batch_no,
            'yield_percentage': str(order.yield_percentage),
            'finished_lot': order.finished_lot.lot_number if order.finished_lot else None
        })


class BatchMaterialConsumptionViewSet(viewsets.ModelViewSet):
    queryset = BatchMaterialConsumption.objects.select_related('order', 'component', 'lot', 'uom').all()
    serializer_class = BatchMaterialConsumptionSerializer
    permission_classes = [permissions.IsAuthenticated]


class BatchProcessStepViewSet(viewsets.ModelViewSet):
    queryset = BatchProcessStep.objects.select_related('order').all()
    serializer_class = BatchProcessStepSerializer
    permission_classes = [permissions.IsAuthenticated]
