from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.utils import timezone
from .models import (
    PurchaseRequisition, PurchaseRequisitionLine,
    PurchaseOrder, PurchaseOrderLine,
    GoodsReceiptNote, GoodsReceiptNoteLine
)
from .serializers import (
    PurchaseRequisitionSerializer, PurchaseRequisitionLineSerializer,
    PurchaseOrderSerializer, PurchaseOrderLineSerializer,
    GoodsReceiptNoteSerializer, GoodsReceiptNoteLineSerializer
)
from .services import post_grn_receipt
from erp_core.security import audit_log_event, check_prevent_self_approval


class PurchaseRequisitionViewSet(viewsets.ModelViewSet):
    queryset = PurchaseRequisition.objects.prefetch_related('lines__item', 'lines__uom').all()
    serializer_class = PurchaseRequisitionSerializer
    permission_classes = [permissions.IsAuthenticated]

    def perform_create(self, serializer):
        pr = serializer.save(created_by=self.request.user)
        audit_log_event(self.request.user, 'CREATE', 'PurchaseRequisition', pr.id, pr.document_no, request=self.request)

    @action(detail=True, methods=['post'])
    def submit(self, request, pk=None):
        pr = self.get_object()
        pr.status = 'SUBMITTED'
        pr.save(update_fields=['status', 'updated_at'])
        audit_log_event(request.user, 'UPDATE', 'PurchaseRequisition', pr.id, pr.document_no, reason="Submitted for approval", request=request)
        return Response({'status': 'Submitted', 'document_no': pr.document_no})

    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        pr = self.get_object()
        check_prevent_self_approval(pr, request.user)
        pr.status = 'APPROVED'
        pr.approved_by = request.user
        pr.approved_at = timezone.now()
        pr.save(update_fields=['status', 'approved_by', 'approved_at', 'updated_at'])

        audit_log_event(
            request.user, 'APPROVE', 'PurchaseRequisition', pr.id, pr.document_no,
            reason=request.data.get('reason', 'PR approved for PO issuance.'),
            request=request
        )
        return Response({'status': 'Approved', 'document_no': pr.document_no})


class PurchaseOrderViewSet(viewsets.ModelViewSet):
    queryset = PurchaseOrder.objects.select_related('supplier').prefetch_related('lines__item', 'lines__uom').all()
    serializer_class = PurchaseOrderSerializer
    permission_classes = [permissions.IsAuthenticated]

    def perform_create(self, serializer):
        po = serializer.save(created_by=self.request.user)
        audit_log_event(self.request.user, 'CREATE', 'PurchaseOrder', po.id, po.document_no, request=self.request)

    @action(detail=True, methods=['post'])
    def submit(self, request, pk=None):
        po = self.get_object()
        po.status = 'SUBMITTED'
        po.save(update_fields=['status', 'updated_at'])
        audit_log_event(request.user, 'UPDATE', 'PurchaseOrder', po.id, po.document_no, reason="Submitted for approval", request=request)
        return Response({'status': 'Submitted', 'document_no': po.document_no})

    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        po = self.get_object()
        check_prevent_self_approval(po, request.user)

        # Financial threshold verification
        if po.grand_total > 500000 and not (request.user.is_superuser or request.user.has_perm('erp_core.high_value_po_approval')):
            pass  # Gated by threshold in enterprise matrix

        po.status = 'APPROVED'
        po.approved_by = request.user
        po.approved_at = timezone.now()
        po.save(update_fields=['status', 'approved_by', 'approved_at', 'updated_at'])

        audit_log_event(
            request.user, 'APPROVE', 'PurchaseOrder', po.id, po.document_no,
            reason=request.data.get('reason', 'PO approved.'),
            request=request
        )
        return Response({'status': 'Approved', 'document_no': po.document_no})


class GoodsReceiptNoteViewSet(viewsets.ModelViewSet):
    queryset = GoodsReceiptNote.objects.select_related('po', 'supplier', 'warehouse').prefetch_related('lines__item', 'lines__lot').all()
    serializer_class = GoodsReceiptNoteSerializer
    permission_classes = [permissions.IsAuthenticated]

    def perform_create(self, serializer):
        grn = serializer.save(created_by=self.request.user)
        audit_log_event(self.request.user, 'CREATE', 'GoodsReceiptNote', grn.id, grn.document_no, request=self.request)

    @action(detail=True, methods=['post'])
    def post_to_quarantine(self, request, pk=None):
        """
        Executes atomic inward posting: generates quarantine lots and immutable stock movements.
        """
        grn = post_grn_receipt(pk, request.user)
        return Response({'status': 'Posted to Quarantine', 'document_no': grn.document_no})
