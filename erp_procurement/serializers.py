from rest_framework import serializers
from .models import (
    PurchaseRequisition, PurchaseRequisitionLine,
    PurchaseOrder, PurchaseOrderLine,
    GoodsReceiptNote, GoodsReceiptNoteLine
)


class PurchaseRequisitionLineSerializer(serializers.ModelSerializer):
    item_name = serializers.CharField(source='item.name', read_only=True)
    item_code = serializers.CharField(source='item.item_code', read_only=True)
    uom_code = serializers.CharField(source='uom.code', read_only=True)

    class Meta:
        model = PurchaseRequisitionLine
        fields = '__all__'


class PurchaseRequisitionSerializer(serializers.ModelSerializer):
    lines = PurchaseRequisitionLineSerializer(many=True, read_only=True)
    created_by_name = serializers.CharField(source='created_by.username', read_only=True)

    class Meta:
        model = PurchaseRequisition
        fields = '__all__'


class PurchaseOrderLineSerializer(serializers.ModelSerializer):
    item_name = serializers.CharField(source='item.name', read_only=True)
    item_code = serializers.CharField(source='item.item_code', read_only=True)
    uom_code = serializers.CharField(source='uom.code', read_only=True)

    class Meta:
        model = PurchaseOrderLine
        fields = '__all__'


class PurchaseOrderSerializer(serializers.ModelSerializer):
    supplier_name = serializers.CharField(source='supplier.legal_name', read_only=True)
    lines = PurchaseOrderLineSerializer(many=True, read_only=True)
    created_by_name = serializers.CharField(source='created_by.username', read_only=True)

    def validate(self, attrs):
        order_date = attrs.get('order_date') or (self.instance.order_date if self.instance else None)
        delivery_date = attrs.get('expected_delivery_date') or (self.instance.expected_delivery_date if self.instance else None)
        if order_date and delivery_date and delivery_date < order_date:
            raise serializers.ValidationError({"expected_delivery_date": "Expected delivery date cannot be before order date."})
        supplier = attrs.get('supplier') or (self.instance.supplier if self.instance else None)
        if supplier and supplier.status in ['DISQUALIFIED', 'BLOCKED']:
            raise serializers.ValidationError({"supplier": f"Supplier {supplier.legal_name} has status {supplier.status} and cannot be issued orders."})
        return attrs

    class Meta:
        model = PurchaseOrder
        fields = '__all__'


class GoodsReceiptNoteLineSerializer(serializers.ModelSerializer):
    item_name = serializers.CharField(source='item.name', read_only=True)
    item_code = serializers.CharField(source='item.item_code', read_only=True)
    uom_code = serializers.CharField(source='uom.code', read_only=True)
    lot_number = serializers.CharField(source='lot.lot_number', read_only=True)

    def validate(self, attrs):
        mfg = attrs.get('manufacturing_date') or (self.instance.manufacturing_date if self.instance else None)
        exp = attrs.get('expiry_date') or (self.instance.expiry_date if self.instance else None)
        if mfg and exp and exp <= mfg:
            raise serializers.ValidationError({"expiry_date": "Expiry date must be strictly after manufacturing date."})
        recv_qty = attrs.get('received_qty') if 'received_qty' in attrs else (self.instance.received_qty if self.instance else None)
        if recv_qty is not None and recv_qty <= 0:
            raise serializers.ValidationError({"received_qty": "Received quantity must be greater than zero."})
        return attrs

    class Meta:
        model = GoodsReceiptNoteLine
        fields = '__all__'


class GoodsReceiptNoteSerializer(serializers.ModelSerializer):
    po_no = serializers.CharField(source='po.document_no', read_only=True)
    supplier_name = serializers.CharField(source='supplier.legal_name', read_only=True)
    warehouse_name = serializers.CharField(source='warehouse.name', read_only=True)
    lines = GoodsReceiptNoteLineSerializer(many=True, read_only=True)

    class Meta:
        model = GoodsReceiptNote
        fields = '__all__'
