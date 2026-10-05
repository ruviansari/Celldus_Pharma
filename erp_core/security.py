from rest_framework import permissions
from rest_framework.exceptions import PermissionDenied
from django.utils import timezone
from .models import AuditLog, ERPUserRole


def get_client_ip(request):
    """Safely extracts client IP taking into account proxies/load balancers."""
    if not request:
        return None
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        return x_forwarded_for.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')


def audit_log_event(
    user,
    action: str,
    entity_name: str,
    entity_id: str,
    document_no: str = '',
    reason: str = '',
    changes: dict = None,
    request = None,
    branch = None
):
    """
    Creates an immutable 21 CFR Part 11 compliant audit log entry.
    """
    ip = get_client_ip(request) if request else None
    user_agent = request.META.get('HTTP_USER_AGENT', '') if request else ''

    return AuditLog.objects.create(
        user=user if (user and user.is_authenticated) else None,
        action=action,
        entity_name=entity_name,
        entity_id=str(entity_id),
        document_no=document_no,
        branch=branch,
        reason=reason or '',
        changes=changes or {},
        ip_address=ip,
        user_agent=user_agent[:500]
    )


class HasAnyERPRole(permissions.BasePermission):
    """
    Verifies that the authenticated user possesses at least one of the specified ERP roles,
    or is a superuser.
    """
    allowed_roles = []

    def __init__(self, *roles):
        if roles:
            self.allowed_roles = roles

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False

        if request.user.is_superuser:
            return True

        user_roles = ERPUserRole.objects.filter(user=request.user).values_list('role', flat=True)
        required = getattr(view, 'required_roles', self.allowed_roles)

        if not required:
            return True

        has_role = any(r in user_roles for r in required)
        if not has_role and 'AUDITOR' in user_roles and request.method in permissions.SAFE_METHODS:
            # Auditors are granted read-only safe methods
            return True

        return has_role


class IsQAApprover(permissions.BasePermission):
    """Restricted to QA Approver role or Superuser."""
    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        if request.user.is_superuser:
            return True
        return ERPUserRole.objects.filter(user=request.user, role='QA_APPROVER').exists()


class IsQCAnalyst(permissions.BasePermission):
    """Restricted to QC Analyst or QA Approver."""
    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        if request.user.is_superuser:
            return True
        return ERPUserRole.objects.filter(user=request.user, role__in=['QC_ANALYST', 'QA_APPROVER']).exists()


class IsWarehouseStaff(permissions.BasePermission):
    """Restricted to Warehouse staff or Admin."""
    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        if request.user.is_superuser:
            return True
        return ERPUserRole.objects.filter(user=request.user, role__in=['WAREHOUSE', 'ADMIN']).exists()


class IsPurchaseStaff(permissions.BasePermission):
    """Restricted to Purchase staff or Admin."""
    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        if request.user.is_superuser:
            return True
        return ERPUserRole.objects.filter(user=request.user, role__in=['PURCHASE', 'ADMIN']).exists()


def check_prevent_self_approval(document, user):
    """
    Mandatory compliance control: Requester / Creator cannot approve their own documents
    (PR, PO, QA Disposition, Deviation, Payment).
    """
    if getattr(document, 'created_by_id', None) == user.id and not user.is_superuser:
        raise PermissionDenied("Segregation of Duties Violation: You cannot approve a document you created.")
