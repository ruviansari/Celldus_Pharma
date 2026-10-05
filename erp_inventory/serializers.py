from rest_framework import serializers
from .models import InventoryLot, StockLedger, CycleCountSession, CycleCountLine


class InventoryLotSerializer(serializers.ModelSerializer):
    item_code = serializers.CharField(source='item.item_code', read_only=True)
    item_name = serializers.CharField(source='item.name', read_only=True)
    warehouse_name = serializers.CharField(source='warehouse.name', read_only=True)
    bin_code = serializers.CharField(source='bin.bin_code', read_only=True)
    uom_code = serializers.CharField(source='uom.code', read_only=True)
    quantity_available = serializers.DecimalField(max_digits=14, decimal_places=4, read_only=True)
    is_eligible_for_issue = serializers.BooleanField(read_only=True)

    def validate(self, attrs):
        mfg = attrs.get('manufacturing_date') or (self.instance.manufacturing_date if self.instance else None)
        exp = attrs.get('expiry_date') or (self.instance.expiry_date if self.instance else None)
        if mfg and exp and exp <= mfg:
            raise serializers.ValidationError({"expiry_date": "Batch expiry date must be strictly after manufacturing date."})
        
        q_on_hand = attrs.get('quantity_on_hand') if 'quantity_on_hand' in attrs else (self.instance.quantity_on_hand if self.instance else None)
        q_reserved = attrs.get('quantity_reserved') if 'quantity_reserved' in attrs else (self.instance.quantity_reserved if self.instance else None)
        if q_on_hand is not None and q_reserved is not None and q_reserved > q_on_hand:
            raise serializers.ValidationError({"quantity_reserved": f"Reserved quantity ({q_reserved}) cannot exceed quantity on hand ({q_on_hand})."})
        return attrs

    class Meta:
        model = InventoryLot
        fields = '__all__'


class StockLedgerSerializer(serializers.ModelSerializer):
    item_code = serializers.CharField(source='item.item_code', read_only=True)
    item_name = serializers.CharField(source='item.name', read_only=True)
    lot_number = serializers.CharField(source='lot.lot_number', read_only=True)
    batch_no = serializers.CharField(source='lot.batch_no', read_only=True)
    uom_code = serializers.CharField(source='uom.code', read_only=True)
    from_warehouse_code = serializers.CharField(source='from_warehouse.code', read_only=True)
    to_warehouse_code = serializers.CharField(source='to_warehouse.code', read_only=True)
    username = serializers.CharField(source='user.username', read_only=True)

    class Meta:
        model = StockLedger
        fields = '__all__'


class CycleCountLineSerializer(serializers.ModelSerializer):
    item_code = serializers.CharField(source='item.item_code', read_only=True)
    lot_number = serializers.CharField(source='lot.lot_number', read_only=True)

    class Meta:
        model = CycleCountLine
        fields = '__all__'


class CycleCountSessionSerializer(serializers.ModelSerializer):
    warehouse_name = serializers.CharField(source='warehouse.name', read_only=True)
    lines = CycleCountLineSerializer(many=True, read_only=True)

    class Meta:
        model = CycleCountSession
        fields = '__all__'
