"""
Role-Based Access Control and Anti-IDOR Permission Helpers for Tracking & SFA.
Strictly prevents horizontal privilege escalation (IDOR) across employees and managers.
"""
from django.db.models import Q
from django.utils import timezone
from rest_framework import permissions
from rest_framework.exceptions import PermissionDenied, NotFound
from erp_core.models import ERPUserRole, Branch
from erp_hr.models import Employee


def get_authenticated_employee(user) -> Employee:
    """
    Safely retrieves the Employee master record for the currently authenticated User.
    Raises PermissionDenied if the user does not have an active employee profile.
    """
    if not user or not user.is_authenticated:
        raise PermissionDenied("Authentication credentials were not provided.")

    try:
        emp = Employee.objects.select_related('manager', 'territory', 'branch').get(user=user)
        if not emp.is_active:
            raise PermissionDenied("Your employee account is currently deactivated. Contact HR.")
        return emp
    except Employee.DoesNotExist:
        # If user is a superuser or staff member, auto-link/provision an executive employee profile for testing
        if user.is_superuser or user.is_staff:
            emp, _ = Employee.objects.get_or_create(
                user=user,
                defaults={
                    'employee_code': f"EMP-ADM-{user.id:03d}",
                    'first_name': user.first_name or user.username.capitalize(),
                    'last_name': user.last_name or 'Director',
                    'email': user.email or f"{user.username}@cellduspharma.com",
                    'department': 'SALES',
                    'designation': 'National Sales Director',
                    'sales_tier': 'NSM',
                    'joining_date': timezone.now().date(),
                    'branch': Branch.objects.first(),
                    'is_active': True,
                }
            )
            return emp
        raise PermissionDenied("No active Employee profile linked to this user account.")


def is_system_or_hr_admin(user) -> bool:
    """Returns True if user is a Superuser, Staff, or possesses Admin / HR Enterprise role."""
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser or user.is_staff:
        return True
    return ERPUserRole.objects.filter(
        user=user,
        role__in=['ADMIN', 'HR_PAYROLL']
    ).exists()


def is_sales_manager(user) -> bool:
    """Returns True if user is a designated Sales Manager (ASM, RSM, NSM) or Sales Admin."""
    if is_system_or_hr_admin(user):
        return True
    emp = getattr(user, 'employee_profile', None)
    if emp and emp.sales_tier in ['ASM', 'RSM', 'NSM']:
        return True
    return ERPUserRole.objects.filter(user=user, role='SALES_CRM').exists()


def get_subordinate_ids_recursive(employee: Employee) -> list:
    """
    Recursively fetches all subordinate employee IDs reporting to this manager.
    Supports multi-level hierarchies: NSM -> RSM -> ASM -> MR.
    """
    if not employee:
        return []

    direct_subordinates = list(Employee.objects.filter(manager=employee, is_active=True).values_list('id', flat=True))
    all_subordinates = list(direct_subordinates)

    for sub_id in direct_subordinates:
        sub_emp = Employee.objects.filter(id=sub_id).first()
        if sub_emp:
            all_subordinates.extend(get_subordinate_ids_recursive(sub_emp))

    return list(set(all_subordinates))


def can_user_access_employee(user, target_employee: Employee) -> bool:
    """
    Anti-IDOR validation: Ensures an authenticated user is authorized to view
    or manage target_employee's data.
    """
    if not user or not user.is_authenticated:
        return False
    if is_system_or_hr_admin(user):
        return True

    current_emp = getattr(user, 'employee_profile', None)
    if not current_emp:
        return False

    # 1. User accessing their own data
    if current_emp.id == target_employee.id:
        return True

    # 2. Manager accessing their direct or indirect subordinate
    subordinate_ids = get_subordinate_ids_recursive(current_emp)
    if target_employee.id in subordinate_ids:
        return True

    # 3. Territory manager check
    if target_employee.territory and target_employee.territory.manager_id == current_emp.id:
        return True

    return False


class IsFieldForceAuthenticated(permissions.BasePermission):
    """Ensures user is authenticated and possesses a valid Employee record or staff permissions."""
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if request.user.is_superuser or request.user.is_staff:
            return True
        return hasattr(request.user, 'employee_profile')


class IsManagerOrAdmin(permissions.BasePermission):
    """Restricted to Managers (ASM/RSM/NSM) or Admins."""
    def has_permission(self, request, view):
        return is_sales_manager(request.user)
