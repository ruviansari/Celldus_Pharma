import uuid
from decimal import Decimal
from django.db import models
from django.conf import settings
from django.utils import timezone
from erp_core.models import ERPBaseModel, ERPDocumentModel, Branch, DocumentSequence


class Employee(ERPBaseModel):
    """
    Employee Master for Pharma Operations, QA, Warehouse, and Administration.
    """
    DEPARTMENT_CHOICES = (
        ('QA', 'Quality Assurance (QA)'),
        ('QC', 'Quality Control (QC)'),
        ('PRODUCTION', 'Manufacturing & Production'),
        ('WAREHOUSE', 'Warehouse & Stores'),
        ('PURCHASE', 'Purchase & Procurement'),
        ('SALES', 'Sales & Marketing'),
        ('FINANCE', 'Accounts & Finance'),
        ('HR', 'Human Resources'),
        ('MAINTENANCE', 'Engineering & Maintenance'),
    )

    employee_code = models.CharField(max_length=30, unique=True, db_index=True)
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    user = models.OneToOneField(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='employee_profile')

    department = models.CharField(max_length=30, choices=DEPARTMENT_CHOICES)
    designation = models.CharField(max_length=100)
    branch = models.ForeignKey(Branch, on_delete=models.PROTECT)
    joining_date = models.DateField()

    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=30, blank=True)

    base_salary = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    bank_account_no = models.CharField(max_length=50, blank=True)
    bank_ifsc = models.CharField(max_length=20, blank=True)

    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"[{self.employee_code}] {self.first_name} {self.last_name} ({self.department})"


class AttendanceRecord(ERPBaseModel):
    """
    Daily attendance punch record.
    """
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='attendance_records')
    date = models.DateField(default=timezone.now, db_index=True)
    in_time = models.TimeField(null=True, blank=True)
    out_time = models.TimeField(null=True, blank=True)
    status = models.CharField(max_length=20, default='PRESENT', choices=(('PRESENT', 'Present'), ('ABSENT', 'Absent'), ('HALF_DAY', 'Half Day'), ('ON_LEAVE', 'On Leave')))
    overtime_hours = models.DecimalField(max_digits=4, decimal_places=2, default=Decimal('0.00'))

    class Meta:
        unique_together = ('employee', 'date')

    def __str__(self):
        return f"{self.employee.employee_code} on {self.date}: {self.status}"


class LeaveApplication(ERPDocumentModel):
    """
    Employee leave application with manager approval.
    """
    LEAVE_TYPES = (
        ('CASUAL', 'Casual Leave (CL)'),
        ('SICK', 'Medical / Sick Leave (SL)'),
        ('EARNED', 'Earned / Paid Leave (EL)'),
        ('UNPAID', 'Leave Without Pay (LWP)'),
    )

    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='leaves')
    leave_type = models.CharField(max_length=20, choices=LEAVE_TYPES)
    from_date = models.DateField()
    to_date = models.DateField()
    days_count = models.DecimalField(max_digits=4, decimal_places=1, default=Decimal('1.0'))
    reason = models.TextField()

    status = models.CharField(max_length=20, default='SUBMITTED', choices=(('SUBMITTED', 'Submitted'), ('APPROVED', 'Approved'), ('REJECTED', 'Rejected')))

    def save(self, *args, **kwargs):
        if not self.document_no:
            self.document_no = DocumentSequence.get_next_number('LEAVE', self.branch)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.document_no} - {self.employee.first_name} ({self.leave_type}) [{self.status}]"
