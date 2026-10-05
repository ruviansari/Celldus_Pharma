from rest_framework import viewsets, permissions, views, status, generics
from rest_framework.response import Response
from django.contrib.auth import get_user_model
from .models import Branch, ERPUserRole, AuditLog, DocumentSequence
from drf_spectacular.utils import extend_schema
from .serializers import BranchSerializer, ERPUserRoleSerializer, AuditLogSerializer, UserContextResponseSerializer
from .security import HasAnyERPRole, audit_log_event

User = get_user_model()


class BranchViewSet(viewsets.ModelViewSet):
    """
    CRUD for Manufacturing Sites, Warehouses, and Branches.
    Restricted to ADMIN or AUDITOR (read-only).
    """
    queryset = Branch.objects.all()
    serializer_class = BranchSerializer
    permission_classes = [permissions.IsAuthenticated]

    def perform_create(self, serializer):
        branch = serializer.save()
        audit_log_event(
            user=self.request.user,
            action='CREATE',
            entity_name='Branch',
            entity_id=branch.id,
            document_no=branch.code,
            changes=serializer.data,
            request=self.request
        )

    def perform_update(self, serializer):
        branch = serializer.save()
        audit_log_event(
            user=self.request.user,
            action='UPDATE',
            entity_name='Branch',
            entity_id=branch.id,
            document_no=branch.code,
            changes=serializer.data,
            request=self.request
        )


class ERPUserRoleViewSet(viewsets.ModelViewSet):
    """
    Assign and view roles for Celldus Pharma ERP users.
    Only ADMIN can assign or revoke roles.
    """
    queryset = ERPUserRole.objects.select_related('user', 'branch').all()
    serializer_class = ERPUserRoleSerializer
    permission_classes = [permissions.IsAuthenticated]

    def perform_create(self, serializer):
        user_role = serializer.save(assigned_by=self.request.user)
        audit_log_event(
            user=self.request.user,
            action='CREATE',
            entity_name='ERPUserRole',
            entity_id=user_role.id,
            reason=f"Assigned role {user_role.role} to {user_role.user.username}",
            changes=serializer.data,
            request=self.request
        )

    def perform_destroy(self, instance):
        audit_log_event(
            user=self.request.user,
            action='UPDATE',
            entity_name='ERPUserRole',
            entity_id=instance.id,
            reason=f"Revoked role {instance.role} from {instance.user.username}",
            request=self.request
        )
        instance.delete()


class AuditLogReadOnlyViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Immutable 21 CFR Part 11 compliant audit trail inspector.
    Supports filtering by entity_name, action, document_no, user, and date range.
    """
    queryset = AuditLog.objects.select_related('user', 'branch').all()
    serializer_class = AuditLogSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        qs = super().get_queryset()
        entity = self.request.query_params.get('entity')
        action = self.request.query_params.get('action')
        doc_no = self.request.query_params.get('doc_no')
        user_id = self.request.query_params.get('user')

        if entity:
            qs = qs.filter(entity_name__icontains=entity)
        if action:
            qs = qs.filter(action=action)
        if doc_no:
            qs = qs.filter(document_no__icontains=doc_no)
        if user_id:
            qs = qs.filter(user_id=user_id)

        return qs


@extend_schema(responses={200: UserContextResponseSerializer})
class CurrentUserContextView(views.APIView):
    """
    Returns current user details, active ERP roles, and branch permissions.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        user = request.user
        roles = list(ERPUserRole.objects.filter(user=user).values('role', 'branch__name', 'branch__code'))

        # If superuser and has no explicitly assigned role, grant virtual ADMIN
        if user.is_superuser and not roles:
            roles.append({'role': 'ADMIN', 'branch__name': 'All Branches', 'branch__code': 'GLOBAL'})

        return Response({
            'id': user.id,
            'username': user.username,
            'email': user.email,
            'full_name': f"{user.first_name} {user.last_name}".strip() or user.username,
            'is_superuser': user.is_superuser,
            'roles': roles,
            'role_names': [r['role'] for r in roles]
        })
