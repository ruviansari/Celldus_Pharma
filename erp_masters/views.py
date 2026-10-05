from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.utils import timezone
from .models import (
    UnitOfMeasure, UOMConversion, Warehouse, StorageBin,
    ItemMaster, SupplierMaster, CustomerMaster,
    QualitySpecification, SpecificationParameter,
    BOMHeader, BOMLine
)
from .serializers import (
    UnitOfMeasureSerializer, UOMConversionSerializer, WarehouseSerializer, StorageBinSerializer,
    ItemMasterSerializer, SupplierMasterSerializer, CustomerMasterSerializer,
    QualitySpecificationSerializer, SpecificationParameterSerializer,
    BOMHeaderSerializer, BOMLineSerializer
)
from erp_core.security import audit_log_event, check_prevent_self_approval


class UnitOfMeasureViewSet(viewsets.ModelViewSet):
    queryset = UnitOfMeasure.objects.all()
    serializer_class = UnitOfMeasureSerializer
    permission_classes = [permissions.IsAuthenticated]

    def perform_create(self, serializer):
        uom = serializer.save(created_by=self.request.user)
        audit_log_event(self.request.user, 'CREATE', 'UnitOfMeasure', uom.id, uom.code, request=self.request)


class UOMConversionViewSet(viewsets.ModelViewSet):
    queryset = UOMConversion.objects.select_related('from_uom', 'to_uom').all()
    serializer_class = UOMConversionSerializer
    permission_classes = [permissions.IsAuthenticated]


class WarehouseViewSet(viewsets.ModelViewSet):
    queryset = Warehouse.objects.select_related('branch').prefetch_related('bins').all()
    serializer_class = WarehouseSerializer
    permission_classes = [permissions.IsAuthenticated]

    def perform_create(self, serializer):
        wh = serializer.save(created_by=self.request.user)
        audit_log_event(self.request.user, 'CREATE', 'Warehouse', wh.id, wh.code, request=self.request)


class StorageBinViewSet(viewsets.ModelViewSet):
    queryset = StorageBin.objects.select_related('warehouse').all()
    serializer_class = StorageBinSerializer
    permission_classes = [permissions.IsAuthenticated]


class ItemMasterViewSet(viewsets.ModelViewSet):
    queryset = ItemMaster.objects.select_related('base_uom', 'purchase_uom', 'issue_uom').all()
    serializer_class = ItemMasterSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        qs = super().get_queryset()
        item_type = self.request.query_params.get('item_type')
        search = self.request.query_params.get('search')
        if item_type:
            qs = qs.filter(item_type=item_type)
        if search:
            qs = qs.filter(name__icontains=search) | qs.filter(item_code__icontains=search) | qs.filter(generic_name__icontains=search)
        return qs

    def perform_create(self, serializer):
        item = serializer.save(created_by=self.request.user)
        audit_log_event(self.request.user, 'CREATE', 'ItemMaster', item.id, item.item_code, request=self.request)

    def perform_update(self, serializer):
        item = serializer.save(updated_by=self.request.user)
        audit_log_event(self.request.user, 'UPDATE', 'ItemMaster', item.id, item.item_code, request=self.request)


class SupplierMasterViewSet(viewsets.ModelViewSet):
    queryset = SupplierMaster.objects.all()
    serializer_class = SupplierMasterSerializer
    permission_classes = [permissions.IsAuthenticated]

    def perform_create(self, serializer):
        supplier = serializer.save(created_by=self.request.user)
        audit_log_event(self.request.user, 'CREATE', 'SupplierMaster', supplier.id, supplier.supplier_code, request=self.request)

    def perform_update(self, serializer):
        supplier = serializer.save(updated_by=self.request.user)
        audit_log_event(self.request.user, 'UPDATE', 'SupplierMaster', supplier.id, supplier.supplier_code, request=self.request)


class CustomerMasterViewSet(viewsets.ModelViewSet):
    queryset = CustomerMaster.objects.all()
    serializer_class = CustomerMasterSerializer
    permission_classes = [permissions.IsAuthenticated]

    def perform_create(self, serializer):
        cust = serializer.save(created_by=self.request.user)
        audit_log_event(self.request.user, 'CREATE', 'CustomerMaster', cust.id, cust.customer_code, request=self.request)

    def perform_update(self, serializer):
        cust = serializer.save(updated_by=self.request.user)
        audit_log_event(self.request.user, 'UPDATE', 'CustomerMaster', cust.id, cust.customer_code, request=self.request)


class QualitySpecificationViewSet(viewsets.ModelViewSet):
    queryset = QualitySpecification.objects.select_related('item').prefetch_related('parameters').all()
    serializer_class = QualitySpecificationSerializer
    permission_classes = [permissions.IsAuthenticated]

    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        spec = self.get_object()
        check_prevent_self_approval(spec, request.user)
        spec.is_approved = True
        spec.approved_by = request.user
        spec.save(update_fields=['is_approved', 'approved_by', 'updated_at'])

        audit_log_event(
            request.user, 'APPROVE', 'QualitySpecification', spec.id, spec.spec_code,
            reason=request.data.get('reason', 'Quality specification approved for active release testing.'),
            request=request
        )
        return Response({'status': 'Approved', 'spec_code': spec.spec_code})


class SpecificationParameterViewSet(viewsets.ModelViewSet):
    queryset = SpecificationParameter.objects.all()
    serializer_class = SpecificationParameterSerializer
    permission_classes = [permissions.IsAuthenticated]


class BOMHeaderViewSet(viewsets.ModelViewSet):
    queryset = BOMHeader.objects.select_related('product', 'batch_uom').prefetch_related('lines__component').all()
    serializer_class = BOMHeaderSerializer
    permission_classes = [permissions.IsAuthenticated]

    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        bom = self.get_object()
        check_prevent_self_approval(bom, request.user)
        bom.status = 'APPROVED'
        bom.approved_by = request.user
        bom.approved_at = timezone.now()
        bom.save(update_fields=['status', 'approved_by', 'approved_at', 'updated_at'])

        audit_log_event(
            request.user, 'APPROVE', 'BOMHeader', bom.id, bom.bom_code,
            reason=request.data.get('reason', 'BOM verified and released for manufacturing orders.'),
            request=request
        )
        return Response({'status': 'Approved', 'bom_code': bom.bom_code})


class BOMLineViewSet(viewsets.ModelViewSet):
    queryset = BOMLine.objects.select_related('bom', 'component', 'uom').all()
    serializer_class = BOMLineSerializer
    permission_classes = [permissions.IsAuthenticated]
