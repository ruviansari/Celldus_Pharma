from django.contrib import admin
from .models import Branch, ERPUserRole, AuditLog, DocumentSequence, IdempotencyKey


@admin.register(Branch)
class BranchAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'site_type', 'city', 'state', 'is_active')
    search_fields = ('code', 'name', 'gstin')
    list_filter = ('site_type', 'is_active')


@admin.register(ERPUserRole)
class ERPUserRoleAdmin(admin.ModelAdmin):
    list_display = ('user', 'role', 'branch', 'assigned_at')
    list_filter = ('role', 'branch')
    search_fields = ('user__username', 'role')


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ('timestamp', 'user', 'action', 'entity_name', 'document_no', 'ip_address')
    list_filter = ('action', 'entity_name')
    search_fields = ('entity_id', 'document_no', 'user__username', 'reason')
    readonly_fields = [f.name for f in AuditLog._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False  # Strictly immutable!


@admin.register(DocumentSequence)
class DocumentSequenceAdmin(admin.ModelAdmin):
    list_display = ('prefix', 'financial_year', 'branch', 'last_sequence')
    list_filter = ('prefix', 'financial_year')
