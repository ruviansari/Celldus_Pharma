from django.contrib import admin
from .models import QCInspectionRequest, QCTestResult, QADispositionRecord, QualityDeviation, ProductRecall


class QCTestResultInline(admin.TabularInline):
    model = QCTestResult
    extra = 1


@admin.register(QCInspectionRequest)
class QCInspectionRequestAdmin(admin.ModelAdmin):
    list_display = ('document_no', 'lot', 'item', 'specification', 'status', 'overall_test_result')
    list_filter = ('status', 'overall_test_result')
    search_fields = ('document_no', 'lot__lot_number', 'lot__batch_no')
    inlines = [QCTestResultInline]


@admin.register(QADispositionRecord)
class QADispositionRecordAdmin(admin.ModelAdmin):
    list_display = ('document_no', 'lot', 'disposition', 'authorized_qa_person', 'disposition_date', 'coa_number')
    list_filter = ('disposition',)
    search_fields = ('document_no', 'lot__lot_number', 'coa_number')


@admin.register(QualityDeviation)
class QualityDeviationAdmin(admin.ModelAdmin):
    list_display = ('document_no', 'deviation_title', 'severity', 'affected_lot', 'status')
    list_filter = ('severity', 'status')


@admin.register(ProductRecall)
class ProductRecallAdmin(admin.ModelAdmin):
    list_display = ('document_no', 'lot', 'classification', 'status')
    list_filter = ('classification', 'status')
