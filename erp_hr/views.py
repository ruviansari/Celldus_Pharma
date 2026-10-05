from rest_framework import serializers, viewsets, permissions, status
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


class EmployeeViewSet(viewsets.ModelViewSet):
    queryset = Employee.objects.select_related('branch', 'user').all()
    serializer_class = EmployeeSerializer
    permission_classes = [permissions.IsAuthenticated]


class AttendanceRecordViewSet(viewsets.ModelViewSet):
    queryset = AttendanceRecord.objects.select_related('employee').all()
    serializer_class = AttendanceRecordSerializer
    permission_classes = [permissions.IsAuthenticated]


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
