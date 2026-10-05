from rest_framework import serializers, viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from .models import ChartOfAccount, JournalEntry, JournalLine, ExpenseClaim
from .services import post_journal_entry
from erp_core.security import audit_log_event, check_prevent_self_approval


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


class ExpenseClaimSerializer(serializers.ModelSerializer):
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


class ExpenseClaimViewSet(viewsets.ModelViewSet):
    queryset = ExpenseClaim.objects.all()
    serializer_class = ExpenseClaimSerializer
    permission_classes = [permissions.IsAuthenticated]

    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        expense = self.get_object()
        check_prevent_self_approval(expense, request.user)
        expense.status = 'APPROVED'
        expense.save(update_fields=['status'])
        audit_log_event(request.user, 'APPROVE', 'ExpenseClaim', expense.id, expense.document_no, reason="Expense approved", request=request)
        return Response({'status': 'Approved', 'document_no': expense.document_no})
