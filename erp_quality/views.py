from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.utils import timezone
from .models import QCInspectionRequest, QCTestResult, QADispositionRecord, QualityDeviation, ProductRecall
from .serializers import (
    QCInspectionRequestSerializer, QCTestResultSerializer,
    QADispositionRecordSerializer, QualityDeviationSerializer, ProductRecallSerializer
)
from .services import execute_qa_disposition
from erp_core.security import audit_log_event


class QCInspectionRequestViewSet(viewsets.ModelViewSet):
    queryset = QCInspectionRequest.objects.select_related('lot', 'item', 'specification', 'sampler', 'analyst').prefetch_related('test_results__parameter').all()
    serializer_class = QCInspectionRequestSerializer
    permission_classes = [permissions.IsAuthenticated]

    @action(detail=True, methods=['post'])
    def record_sampling(self, request, pk=None):
        inspection = self.get_object()
        inspection.sample_quantity = request.data.get('sample_quantity', inspection.sample_quantity)
        inspection.sampler = request.user
        inspection.sampled_at = timezone.now()
        inspection.status = 'SAMPLED'
        inspection.save(update_fields=['sample_quantity', 'sampler', 'sampled_at', 'status', 'updated_at'])

        audit_log_event(request.user, 'UPDATE', 'QCInspectionRequest', inspection.id, inspection.document_no, reason="Sampling recorded", request=request)
        return Response({'status': 'Sampled', 'document_no': inspection.document_no})

    @action(detail=True, methods=['post'])
    def execute_disposition(self, request, pk=None):
        """
        Executes formal QA batch release or rejection with attributable reason.
        Body: {"disposition": "RELEASE"|"REJECT"|"HOLD", "reason": "...", "coa_number": "..."}
        """
        disp_choice = request.data.get('disposition')
        reason = request.data.get('reason')
        coa = request.data.get('coa_number', '')

        if not disp_choice or not reason:
            return Response({'error': 'disposition and reason are required.'}, status=status.HTTP_400_BAD_REQUEST)

        disp_record = execute_qa_disposition(pk, disp_choice, reason, request.user, coa)
        return Response({
            'status': 'Disposition Executed',
            'disposition': disp_record.disposition,
            'document_no': disp_record.document_no,
            'lot_number': disp_record.lot.lot_number
        })


class QCTestResultViewSet(viewsets.ModelViewSet):
    queryset = QCTestResult.objects.select_related('inspection', 'parameter').all()
    serializer_class = QCTestResultSerializer
    permission_classes = [permissions.IsAuthenticated]


class QualityDeviationViewSet(viewsets.ModelViewSet):
    queryset = QualityDeviation.objects.select_related('affected_lot').all()
    serializer_class = QualityDeviationSerializer
    permission_classes = [permissions.IsAuthenticated]

    def perform_create(self, serializer):
        dev = serializer.save(created_by=self.request.user)
        audit_log_event(self.request.user, 'CREATE', 'QualityDeviation', dev.id, dev.document_no, request=self.request)


class ProductRecallViewSet(viewsets.ModelViewSet):
    queryset = ProductRecall.objects.select_related('lot').all()
    serializer_class = ProductRecallSerializer
    permission_classes = [permissions.IsAuthenticated]

    def perform_create(self, serializer):
        recall = serializer.save(created_by=self.request.user)
        # Block the lot immediately upon recall initiation
        lot = recall.lot
        lot.status = 'RECALLED'
        lot.save(update_fields=['status'])

        audit_log_event(
            self.request.user,
            'RECALL',
            'ProductRecall',
            recall.id,
            recall.document_no,
            reason=f"Product recall initiated for batch {lot.batch_no}: {recall.recall_reason}",
            request=self.request
        )
