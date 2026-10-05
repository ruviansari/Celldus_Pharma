from rest_framework import serializers
from .models import SalesOrder, SalesOrderLine, SalesOrderLotAllocation, SalesDispatchInvoice


class SalesOrderLotAllocationSerializer(serializers.ModelSerializer):
    lot_number = serializers.CharField(source='lot.lot_number', read_only=True)
    batch_no = serializers.CharField(source='lot.batch_no', read_only=True)
    expiry_date = serializers.CharField(source='lot.expiry_date', read_only=True)
    uom_code = serializers.CharField(source='uom.code', read_only=True)

    class Meta:
        model = SalesOrderLotAllocation
        fields = '__all__'


class SalesOrderLineSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source='product.name', read_only=True)
    product_code = serializers.CharField(source='product.item_code', read_only=True)
    uom_code = serializers.CharField(source='uom.code', read_only=True)
    lot_allocations = SalesOrderLotAllocationSerializer(many=True, read_only=True)

    def validate_discount_percent(self, value):
        if value < 0 or value > 100:
            raise serializers.ValidationError("Discount percentage must be between 0% and 100%.")
        return value

    class Meta:
        model = SalesOrderLine
        fields = '__all__'


class SalesOrderSerializer(serializers.ModelSerializer):
    customer_name = serializers.CharField(source='customer.name', read_only=True)
    lines = SalesOrderLineSerializer(many=True, read_only=True)

    def validate(self, attrs):
        order_date = attrs.get('order_date') or (self.instance.order_date if self.instance else None)
        deliv_date = attrs.get('requested_delivery_date') or (self.instance.requested_delivery_date if self.instance else None)
        if order_date and deliv_date and deliv_date < order_date:
            raise serializers.ValidationError({"requested_delivery_date": "Requested delivery date cannot be before order date."})
        customer = attrs.get('customer') or (self.instance.customer if self.instance else None)
        if customer and getattr(customer, 'status', None) in ['BLOCKED', 'DISQUALIFIED', 'SUSPENDED']:
            raise serializers.ValidationError({"customer": f"Customer {customer.name} is not active and cannot place orders."})
        return attrs

    class Meta:
        model = SalesOrder
        fields = '__all__'


class SalesDispatchInvoiceSerializer(serializers.ModelSerializer):
    order_no = serializers.CharField(source='order.document_no', read_only=True)
    customer_name = serializers.CharField(source='customer.name', read_only=True)

    class Meta:
        model = SalesDispatchInvoice
        fields = '__all__'
