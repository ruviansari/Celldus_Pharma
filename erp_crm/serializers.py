from rest_framework import serializers
from .models import Lead, FollowUpTask, LeadImportBatch


class FollowUpTaskSerializer(serializers.ModelSerializer):
    lead_name = serializers.CharField(source='lead.organization_name', read_only=True)
    assigned_name = serializers.CharField(source='assigned_to.username', read_only=True)

    class Meta:
        model = FollowUpTask
        fields = '__all__'


class LeadSerializer(serializers.ModelSerializer):
    owner_name = serializers.CharField(source='owner.username', read_only=True)
    tasks = FollowUpTaskSerializer(many=True, read_only=True)

    def validate_phone(self, value):
        digits = ''.join(c for c in value if c.isdigit())
        if len(digits) < 10:
            raise serializers.ValidationError("Phone number must have at least 10 digits.")
        return value

    def validate(self, attrs):
        stage = attrs.get('stage') or (self.instance.stage if self.instance else None)
        lost_reason = attrs.get('lost_reason') if 'lost_reason' in attrs else (self.instance.lost_reason if self.instance else '')
        if stage == 'LOST' and not str(lost_reason).strip():
            raise serializers.ValidationError({"lost_reason": "A detailed lost reason is mandatory when marking a lead as LOST."})
        return attrs

    class Meta:
        model = Lead
        fields = '__all__'


class LeadImportBatchSerializer(serializers.ModelSerializer):
    class Meta:
        model = LeadImportBatch
        fields = '__all__'
