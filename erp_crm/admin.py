from django.contrib import admin
from .models import Lead, FollowUpTask, LeadImportBatch


class FollowUpTaskInline(admin.TabularInline):
    model = FollowUpTask
    extra = 1


@admin.register(Lead)
class LeadAdmin(admin.ModelAdmin):
    list_display = ('lead_id', 'organization_name', 'lead_type', 'contact_person', 'phone', 'city', 'stage')
    list_filter = ('lead_type', 'stage')
    search_fields = ('lead_id', 'organization_name', 'phone', 'contact_person')
    inlines = [FollowUpTaskInline]


@admin.register(FollowUpTask)
class FollowUpTaskAdmin(admin.ModelAdmin):
    list_display = ('lead', 'activity_type', 'due_date', 'assigned_to', 'priority', 'status')
    list_filter = ('activity_type', 'status', 'priority')


@admin.register(LeadImportBatch)
class LeadImportBatchAdmin(admin.ModelAdmin):
    list_display = ('batch_no', 'file_name', 'total_rows', 'valid_rows', 'duplicate_rows', 'is_confirmed')
