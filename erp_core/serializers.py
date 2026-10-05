from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import Branch, ERPUserRole, AuditLog, DocumentSequence

User = get_user_model()


class BranchSerializer(serializers.ModelSerializer):
    class Meta:
        model = Branch
        fields = '__all__'


class UserBriefSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username', 'first_name', 'last_name', 'email']


class ERPUserRoleSerializer(serializers.ModelSerializer):
    user_details = UserBriefSerializer(source='user', read_only=True)
    role_display = serializers.CharField(source='get_role_display', read_only=True)
    branch_name = serializers.CharField(source='branch.name', read_only=True)

    class Meta:
        model = ERPUserRole
        fields = ['id', 'user', 'user_details', 'role', 'role_display', 'branch', 'branch_name', 'assigned_at']


class AuditLogSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source='user.username', read_only=True)
    action_display = serializers.CharField(source='get_action_display', read_only=True)
    branch_name = serializers.CharField(source='branch.name', read_only=True)

    class Meta:
        model = AuditLog
        fields = [
            'id', 'timestamp', 'user', 'username', 'action', 'action_display',
            'entity_name', 'entity_id', 'document_no', 'branch', 'branch_name',
            'reason', 'changes', 'ip_address'
        ]


class UserContextResponseSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    username = serializers.CharField()
    email = serializers.EmailField()
    full_name = serializers.CharField()
    is_superuser = serializers.BooleanField()
    roles = serializers.ListField(child=serializers.DictField())
    role_names = serializers.ListField(child=serializers.CharField())

