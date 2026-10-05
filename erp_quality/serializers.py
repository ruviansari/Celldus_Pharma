from rest_framework import serializers
from .models import QCInspectionRequest, QCTestResult, QADispositionRecord, QualityDeviation, ProductRecall


class QCTestResultSerializer(serializers.ModelSerializer):
    parameter_name = serializers.CharField(source='parameter.parameter_name', read_only=True)
    test_method = serializers.CharField(source='parameter.test_method', read_only=True)
    acceptance_criteria = serializers.CharField(source='parameter.acceptance_criteria', read_only=True)

    class Meta:
        model = QCTestResult
        fields = '__all__'


class QCInspectionRequestSerializer(serializers.ModelSerializer):
    item_name = serializers.CharField(source='item.name', read_only=True)
    item_code = serializers.CharField(source='item.item_code', read_only=True)
    lot_number = serializers.CharField(source='lot.lot_number', read_only=True)
    batch_no = serializers.CharField(source='lot.batch_no', read_only=True)
    test_results = QCTestResultSerializer(many=True, read_only=True)

    class Meta:
        model = QCInspectionRequest
        fields = '__all__'


class QADispositionRecordSerializer(serializers.ModelSerializer):
    authorized_qa_name = serializers.CharField(source='authorized_qa_person.username', read_only=True)
    lot_number = serializers.CharField(source='lot.lot_number', read_only=True)

    def validate(self, attrs):
        disposition = attrs.get('disposition') or (self.instance.disposition if self.instance else None)
        coa = attrs.get('coa_number') if 'coa_number' in attrs else (self.instance.coa_number if self.instance else '')
        reason = attrs.get('decision_reason') if 'decision_reason' in attrs else (self.instance.decision_reason if self.instance else '')

        if disposition == 'RELEASE' and not str(coa).strip():
            raise serializers.ValidationError({"coa_number": "A valid Certificate of Analysis (COA) number is mandatory to release a pharmaceutical batch."})
        if not str(reason).strip():
            raise serializers.ValidationError({"decision_reason": "Attributable 21 CFR Part 11 regulatory rationale is mandatory."})
        return attrs

    class Meta:
        model = QADispositionRecord
        fields = '__all__'


class QualityDeviationSerializer(serializers.ModelSerializer):
    lot_number = serializers.CharField(source='affected_lot.lot_number', read_only=True)

    class Meta:
        model = QualityDeviation
        fields = '__all__'


class ProductRecallSerializer(serializers.ModelSerializer):
    lot_number = serializers.CharField(source='lot.lot_number', read_only=True)

    def validate(self, attrs):
        dist = attrs.get('total_distributed_qty') if 'total_distributed_qty' in attrs else (self.instance.total_distributed_qty if self.instance else 0)
        reconciled = attrs.get('total_reconciled_qty') if 'total_reconciled_qty' in attrs else (self.instance.total_reconciled_qty if self.instance else 0)
        if reconciled is not None and dist is not None and reconciled > dist:
            raise serializers.ValidationError({"total_reconciled_qty": "Reconciled quantity cannot exceed total distributed quantity."})
        return attrs

    class Meta:
        model = ProductRecall
        fields = '__all__'
