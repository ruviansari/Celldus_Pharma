from rest_framework import serializers, viewsets, permissions, status, views
from rest_framework.decorators import action
from rest_framework.response import Response
from .models import Employee, AttendanceRecord, LeaveApplication
from erp_core.security import audit_log_event, check_prevent_self_approval


class AttendanceRecordSerializer(serializers.ModelSerializer):
    employee_code = serializers.CharField(source='employee.employee_code', read_only=True)
    employee_name = serializers.CharField(source='employee.first_name', read_only=True)

    class Meta:
        model = AttendanceRecord
        fields = '__all__'


class LeaveApplicationSerializer(serializers.ModelSerializer):
    employee_code = serializers.CharField(source='employee.employee_code', read_only=True)
    employee_name = serializers.CharField(source='employee.first_name', read_only=True)

    class Meta:
        model = LeaveApplication
        fields = '__all__'


class EmployeeSerializer(serializers.ModelSerializer):
    branch_name = serializers.CharField(source='branch.name', read_only=True)

    class Meta:
        model = Employee
        fields = '__all__'
        extra_kwargs = {
            'bank_account_no': {'write_only': True}
        }


class EmployeeProfileSerializer(serializers.ModelSerializer):
    branch_name = serializers.CharField(source='branch.name', read_only=True)
    branch_code = serializers.CharField(source='branch.code', read_only=True)
    territory_name = serializers.CharField(source='territory.name', read_only=True, default='')
    manager_name = serializers.SerializerMethodField()
    username = serializers.CharField(source='user.username', read_only=True, default='')

    class Meta:
        model = Employee
        fields = [
            'id', 'employee_code', 'username', 'first_name', 'last_name',
            'email', 'phone', 'department', 'designation', 'sales_tier',
            'branch', 'branch_name', 'branch_code',
            'territory', 'territory_name',
            'manager', 'manager_name',
            'joining_date', 'bank_account_no', 'bank_ifsc', 'is_active',
            'base_salary'
        ]
        read_only_fields = [
            'id', 'employee_code', 'username', 'department', 'designation',
            'sales_tier', 'branch', 'branch_name', 'branch_code',
            'territory', 'territory_name', 'manager', 'manager_name',
            'joining_date', 'is_active', 'base_salary'
        ]

    def get_manager_name(self, obj):
        if obj.manager:
            return f"{obj.manager.first_name} {obj.manager.last_name}".strip()
        return None


class EmployeeProfileUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Employee
        fields = [
            'first_name', 'last_name', 'email', 'phone',
            'bank_account_no', 'bank_ifsc'
        ]
        extra_kwargs = {
            'first_name': {'required': False},
            'last_name': {'required': False},
            'email': {'required': False},
            'phone': {'required': False},
            'bank_account_no': {'required': False},
            'bank_ifsc': {'required': False},
        }


class EmployeeProfileAPIView(views.APIView if 'views' in globals() else viewsets.views.APIView):
    """
    Dedicated Mobile App API Endpoint for Employee Profile:
    - GET   /api/v1/hr/profile/me/    : Fetch logged-in employee profile
    - PATCH /api/v1/hr/profile/me/    : Update profile details (phone, email, bank details, names)
    - POST  /api/v1/hr/profile/update/: Update profile details
    """
    permission_classes = [permissions.IsAuthenticated]

    def get_employee(self, user):
        emp = getattr(user, 'employee_profile', None)
        if not emp:
            if user.email:
                emp = Employee.objects.filter(email=user.email).first()
            if not emp:
                emp = Employee.objects.filter(employee_code=user.username).first()
            if emp and not emp.user:
                emp.user = user
                emp.save(update_fields=['user'])
        return emp

    def get(self, request):
        emp = self.get_employee(request.user)
        if not emp:
            return Response({
                'success': False,
                'message': 'No employee profile linked to the current user.',
                'error_code': 'NO_EMPLOYEE_PROFILE'
            }, status=status.HTTP_404_NOT_FOUND)

        serializer = EmployeeProfileSerializer(emp)
        return Response({
            'success': True,
            'message': 'Profile retrieved successfully.',
            'data': serializer.data
        }, status=status.HTTP_200_OK)

    def patch(self, request):
        return self.update_profile(request, partial=True)

    def put(self, request):
        return self.update_profile(request, partial=False)

    def post(self, request):
        # Support POST /api/v1/hr/profile/update/ for mobile apps that prefer POST
        return self.update_profile(request, partial=True)

    def update_profile(self, request, partial=True):
        emp = self.get_employee(request.user)
        if not emp:
            return Response({
                'success': False,
                'message': 'No employee profile linked to the current user.',
                'error_code': 'NO_EMPLOYEE_PROFILE'
            }, status=status.HTTP_404_NOT_FOUND)

        serializer = EmployeeProfileUpdateSerializer(emp, data=request.data, partial=partial)
        if not serializer.is_valid():
            return Response({
                'success': False,
                'message': 'Validation error.',
                'errors': serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)

        # Track changes for 21 CFR Part 11 audit log
        changes = {}
        for field, value in serializer.validated_data.items():
            old_val = getattr(emp, field, None)
            if str(old_val) != str(value):
                changes[field] = {'old': str(old_val), 'new': str(value)}

        updated_emp = serializer.save()

        # Synchronize with Django User model if name/email updated
        user = request.user
        user_updated_fields = []
        if 'first_name' in serializer.validated_data and user.first_name != updated_emp.first_name:
            user.first_name = updated_emp.first_name
            user_updated_fields.append('first_name')
        if 'last_name' in serializer.validated_data and user.last_name != updated_emp.last_name:
            user.last_name = updated_emp.last_name
            user_updated_fields.append('last_name')
        if 'email' in serializer.validated_data and user.email != updated_emp.email:
            user.email = updated_emp.email
            user_updated_fields.append('email')

        if user_updated_fields:
            user.save(update_fields=user_updated_fields)

        # Record 21 CFR Part 11 Audit Trail
        audit_log_event(
            user=request.user,
            action='UPDATE',
            entity_name='EmployeeProfile',
            entity_id=str(updated_emp.id),
            document_no=updated_emp.employee_code,
            reason="Employee profile updated via mobile application",
            changes=changes,
            request=request,
            branch=updated_emp.branch
        )

        return Response({
            'success': True,
            'message': 'Profile updated successfully.',
            'data': EmployeeProfileSerializer(updated_emp).data
        }, status=status.HTTP_200_OK)


class EmployeeViewSet(viewsets.ModelViewSet):
    queryset = Employee.objects.select_related('branch', 'user', 'manager', 'territory').all()
    serializer_class = EmployeeSerializer
    permission_classes = [permissions.IsAuthenticated]

    @action(detail=False, methods=['get', 'patch', 'put', 'post'], url_path='me')
    def me(self, request):
        """
        Route: /api/v1/hr/employees/me/
        """
        view = EmployeeProfileAPIView()
        view.request = request
        if request.method == 'GET':
            return view.get(request)
        else:
            return view.update_profile(request, partial=(request.method in ['PATCH', 'POST']))


class IsSuperAdminOrHRForAttendance(permissions.BasePermission):
    """
    Pharma Compliance Rule:
    Allows read access (GET) to authenticated staff/auditors.
    Write access (POST, PUT, PATCH, DELETE) is strictly restricted to
    Super Admin or users with System ADMIN / HR_PAYROLL roles.
    """
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if request.method in permissions.SAFE_METHODS:
            return True
        if request.user.is_superuser or request.user.username.lower() in ['admin', 'superadmin']:
            return True
        from erp_core.models import ERPUserRole
        return ERPUserRole.objects.filter(user=request.user, role__in=['ADMIN', 'HR_PAYROLL']).exists()


class AttendanceRecordViewSet(viewsets.ModelViewSet):
    queryset = AttendanceRecord.objects.select_related('employee').all()
    serializer_class = AttendanceRecordSerializer
    permission_classes = [IsSuperAdminOrHRForAttendance]


class LeaveApplicationViewSet(viewsets.ModelViewSet):
    queryset = LeaveApplication.objects.select_related('employee').all()
    serializer_class = LeaveApplicationSerializer
    permission_classes = [permissions.IsAuthenticated]

    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        leave = self.get_object()
        leave.status = 'APPROVED'
        leave.approved_by = request.user
        leave.save(update_fields=['status', 'approved_by', 'updated_at'])
        audit_log_event(request.user, 'APPROVE', 'LeaveApplication', leave.id, leave.document_no, reason="Leave approved", request=request)
        return Response({'status': 'Approved', 'document_no': leave.document_no})
