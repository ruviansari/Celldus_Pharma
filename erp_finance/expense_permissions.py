"""
Role-Based Access Control & Anti-IDOR Security Permissions for Expense Management.
Strictly enforces Segregation of Duties (SOD) and 21 CFR attributable security.
"""
from rest_framework import permissions
from erp_core.models import ERPUserRole
from erp_crm.tracking_permissions import get_authenticated_employee, get_subordinate_ids_recursive


def is_finance_or_admin(user) -> bool:
    """Returns True if user has Accounts, Finance or System Admin authority."""
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser or user.username.lower() in ['admin', 'superadmin']:
        return True
    return ERPUserRole.objects.filter(user=user, role__in=['ADMIN', 'ACCOUNTS']).exists()


def is_manager_or_admin(user) -> bool:
    """Returns True if user is a designated Manager (ASM/RSM/NSM/Dept Head), Finance, or Admin."""
    if is_finance_or_admin(user):
        return True
    emp = getattr(user, 'employee_profile', None)
    if emp and (emp.subordinates.exists() or emp.sales_tier in ['ASM', 'RSM', 'NSM']):
        return True
    return False


class IsExpenseOwnerOrApprover(permissions.BasePermission):
    """
    Prevents Insecure Direct Object Reference (IDOR):
    - Employees can only see their own claims.
    - Managers can see their subordinate employees' claims.
    - Finance & Admins can audit all claims across branches.
    """
    def has_object_permission(self, request, view, obj):
        if not request.user or not request.user.is_authenticated:
            return False

        if is_finance_or_admin(request.user):
            return True

        curr_emp = getattr(request.user, 'employee_profile', None)
        if not curr_emp:
            return False

        # Owner
        if obj.employee_id == curr_emp.id:
            return True

        # Reporting Manager hierarchy
        sub_ids = get_subordinate_ids_recursive(curr_emp)
        if obj.employee_id in sub_ids:
            return True

        return False
