from rest_framework import serializers, viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from .models import (
    ChartOfAccount, JournalEntry, JournalLine,
    ExpenseClaim, ExpenseCategory, ExpenseSubCategory, ExpenseAttachment
)
from .services import (
    post_journal_entry, submit_expense_claim,
    manager_review_expense, finance_audit_expense, disburse_expense_and_post_gl
)
from .expense_permissions import IsExpenseOwnerOrApprover, is_finance_or_admin, is_manager_or_admin
from erp_core.security import audit_log_event, check_prevent_self_approval
from erp_crm.tracking_permissions import get_subordinate_ids_recursive


class ChartOfAccountSerializer(serializers.ModelSerializer):
    class Meta:
        model = ChartOfAccount
        fields = '__all__'


class JournalLineSerializer(serializers.ModelSerializer):
    account_code = serializers.CharField(source='account.account_code', read_only=True)
    account_name = serializers.CharField(source='account.name', read_only=True)

    def validate(self, attrs):
        debit = attrs.get('debit', getattr(self.instance, 'debit', 0))
        credit = attrs.get('credit', getattr(self.instance, 'credit', 0))
        if debit > 0 and credit > 0:
            raise serializers.ValidationError("A single journal line cannot contain both Debit and Credit amounts.")
        if debit == 0 and credit == 0:
            raise serializers.ValidationError("Journal line must have either a Debit or Credit amount greater than zero.")
        return attrs

    class Meta:
        model = JournalLine
        fields = '__all__'


class JournalEntrySerializer(serializers.ModelSerializer):
    lines = JournalLineSerializer(many=True, read_only=True)

    class Meta:
        model = JournalEntry
        fields = '__all__'


class ExpenseSubCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = ExpenseSubCategory
        fields = '__all__'


class ExpenseCategorySerializer(serializers.ModelSerializer):
    subcategories = ExpenseSubCategorySerializer(many=True, read_only=True)
    gl_account_name = serializers.CharField(source='gl_account.name', read_only=True)

    class Meta:
        model = ExpenseCategory
        fields = '__all__'


class ExpenseAttachmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = ExpenseAttachment
        fields = '__all__'


class ExpenseClaimSerializer(serializers.ModelSerializer):
    employee_code = serializers.CharField(source='employee.employee_code', read_only=True)
    employee_name = serializers.CharField(source='employee.first_name', read_only=True)
    category_name = serializers.CharField(source='expense_category.name', read_only=True)
    sub_category_name = serializers.CharField(source='sub_category.name', read_only=True)
    branch_name = serializers.CharField(source='branch.name', read_only=True)
    attachments = ExpenseAttachmentSerializer(many=True, read_only=True)

    class Meta:
        model = ExpenseClaim
        fields = '__all__'


class ChartOfAccountViewSet(viewsets.ModelViewSet):
    queryset = ChartOfAccount.objects.all()
    serializer_class = ChartOfAccountSerializer
    permission_classes = [permissions.IsAuthenticated]


class JournalEntryViewSet(viewsets.ModelViewSet):
    queryset = JournalEntry.objects.prefetch_related('lines__account').all()
    serializer_class = JournalEntrySerializer
    permission_classes = [permissions.IsAuthenticated]

    @action(detail=True, methods=['post'])
    def post_to_gl(self, request, pk=None):
        journal = post_journal_entry(pk, request.user)
        return Response({'status': 'Posted', 'document_no': journal.document_no})


class ExpenseCategoryViewSet(viewsets.ModelViewSet):
    queryset = ExpenseCategory.objects.prefetch_related('subcategories', 'gl_account').filter(is_active=True)
    serializer_class = ExpenseCategorySerializer
    permission_classes = [permissions.IsAuthenticated]


class ExpenseClaimViewSet(viewsets.ModelViewSet):
    serializer_class = ExpenseClaimSerializer
    permission_classes = [permissions.IsAuthenticated, IsExpenseOwnerOrApprover]

    def get_queryset(self):
        user = self.request.user
        qs = ExpenseClaim.objects.select_related(
            'employee', 'expense_category', 'sub_category', 'branch', 'manager_approver', 'finance_approver'
        ).prefetch_related('attachments').order_by('-created_at')

        # Finance & Admin see all
        if is_finance_or_admin(user):
            return qs

        curr_emp = getattr(user, 'employee_profile', None)
        if not curr_emp:
            return qs.filter(created_by=user)

        # Manager sees own claims + subordinate employees' claims
        sub_ids = get_subordinate_ids_recursive(curr_emp)
        return qs.filter(models.Q(employee=curr_emp) | models.Q(employee_id__in=sub_ids))

    @action(detail=True, methods=['post'])
    def submit(self, request, pk=None):
        claim = self.get_object()
        if claim.status != 'DRAFT':
            return Response({'error': f"Only draft claims can be submitted (current status: {claim.status})."}, status=status.HTTP_400_BAD_REQUEST)
        claim.status = 'SUBMITTED'
        claim.save(update_fields=['status', 'updated_at'])
        audit_log_event(request.user, 'SUBMIT', 'ExpenseClaim', str(claim.id), claim.document_no, reason="Claim submitted for review", request=request)
        return Response({'status': 'Submitted', 'document_no': claim.document_no})

    @action(detail=True, methods=['post'])
    def manager_review(self, request, pk=None):
        action_type = request.data.get('action', 'APPROVE')
        remarks = request.data.get('remarks', '')
        try:
            claim = manager_review_expense(pk, request.user, action=action_type, remarks=remarks, request=request)
            return Response({'status': claim.status, 'document_no': claim.document_no})
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'])
    def finance_audit(self, request, pk=None):
        if not is_finance_or_admin(request.user):
            return Response({'error': "Permission Denied: Only Accounts/Finance Head can sanction expenses."}, status=status.HTTP_403_FORBIDDEN)
        action_type = request.data.get('action', 'APPROVE')
        remarks = request.data.get('remarks', '')
        try:
            claim = finance_audit_expense(pk, request.user, action=action_type, remarks=remarks, request=request)
            return Response({'status': claim.status, 'document_no': claim.document_no})
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'])
    def disburse(self, request, pk=None):
        if not is_finance_or_admin(request.user):
            return Response({'error': "Permission Denied: Only Accounts/Finance Head can disburse payments."}, status=status.HTTP_403_FORBIDDEN)
        utr = request.data.get('payment_utr', '')
        mode = request.data.get('payment_mode', None)
        try:
            claim = disburse_expense_and_post_gl(pk, request.user, payment_utr=utr, payment_mode=mode, request=request)
            return Response({
                'status': claim.status,
                'document_no': claim.document_no,
                'payment_utr': claim.payment_utr,
                'journal_entry': claim.linked_journal.document_no if claim.linked_journal else None
            })
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

