from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.utils import timezone
from .models import Lead, FollowUpTask, LeadImportBatch
from .serializers import LeadSerializer, FollowUpTaskSerializer, LeadImportBatchSerializer
from .services import process_lead_import_rows
from erp_core.security import audit_log_event


class LeadViewSet(viewsets.ModelViewSet):
    queryset = Lead.objects.prefetch_related('tasks').all()
    serializer_class = LeadSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        qs = super().get_queryset()
        stage = self.request.query_params.get('stage')
        territory = self.request.query_params.get('territory')
        search = self.request.query_params.get('search')

        if stage:
            qs = qs.filter(stage=stage)
        if territory:
            qs = qs.filter(territory__icontains=territory)
        if search:
            qs = qs.filter(organization_name__icontains=search) | qs.filter(phone__icontains=search) | qs.filter(contact_person__icontains=search)

        return qs

    def perform_create(self, serializer):
        lead = serializer.save(created_by=self.request.user)
        audit_log_event(self.request.user, 'CREATE', 'Lead', lead.id, lead.lead_id, request=self.request)

    @action(detail=False, methods=['post'])
    def bulk_import(self, request):
        """
        Accepts rows: [{"organization_name": "...", "contact_person": "...", "phone": "..."}, ...]
        and flag "commit": true/false (preview vs execute).
        """
        rows = request.data.get('rows', [])
        commit = request.data.get('commit', False)
        file_name = request.data.get('file_name', 'upload.xlsx')

        if not rows:
            return Response({'error': 'No rows provided.'}, status=status.HTTP_400_BAD_REQUEST)

        res = process_lead_import_rows(rows, file_name, request.user, commit=commit)
        return Response(res)


class FollowUpTaskViewSet(viewsets.ModelViewSet):
    queryset = FollowUpTask.objects.select_related('lead', 'assigned_to').all()
    serializer_class = FollowUpTaskSerializer
    permission_classes = [permissions.IsAuthenticated]

    @action(detail=False, methods=['get'])
    def summary_dashboard(self, request):
        """
        Returns due today, overdue, and completed task metrics.
        """
        today = timezone.now().date()
        due_today = FollowUpTask.objects.filter(due_date=today, status='PENDING').count()
        overdue = FollowUpTask.objects.filter(due_date__lt=today, status='PENDING').count()
        completed = FollowUpTask.objects.filter(status='COMPLETED').count()

        return Response({
            'due_today': due_today,
            'overdue': overdue,
            'completed': completed
        })


class LeadImportBatchViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = LeadImportBatch.objects.all()
    serializer_class = LeadImportBatchSerializer
    permission_classes = [permissions.IsAuthenticated]
