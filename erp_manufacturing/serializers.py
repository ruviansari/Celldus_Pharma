from rest_framework import serializers
from .models import ProductionOrder, BatchMaterialConsumption, BatchProcessStep


class BatchMaterialConsumptionSerializer(serializers.ModelSerializer):
    component_name = serializers.CharField(source='component.name', read_only=True)
    component_code = serializers.CharField(source='component.item_code', read_only=True)
    lot_number = serializers.CharField(source='lot.lot_number', read_only=True)
    uom_code = serializers.CharField(source='uom.code', read_only=True)

    class Meta:
        model = BatchMaterialConsumption
        fields = '__all__'


class BatchProcessStepSerializer(serializers.ModelSerializer):
    operator_name = serializers.CharField(source='operator.username', read_only=True)
    verified_by_name = serializers.CharField(source='verified_by.username', read_only=True)

    class Meta:
        model = BatchProcessStep
        fields = '__all__'


class ProductionOrderSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source='product.name', read_only=True)
    product_code = serializers.CharField(source='product.item_code', read_only=True)
    bom_code = serializers.CharField(source='bom.bom_code', read_only=True)
    uom_code = serializers.CharField(source='uom.code', read_only=True)
    target_warehouse_name = serializers.CharField(source='target_warehouse.name', read_only=True)
    material_consumptions = BatchMaterialConsumptionSerializer(many=True, read_only=True)
    process_steps = BatchProcessStepSerializer(many=True, read_only=True)
    finished_lot_number = serializers.CharField(source='finished_lot.lot_number', read_only=True)

    def validate(self, attrs):
        mfg = attrs.get('manufacturing_date') or (self.instance.manufacturing_date if self.instance else None)
        exp = attrs.get('expiry_date') or (self.instance.expiry_date if self.instance else None)
        if mfg and exp and exp <= mfg:
            raise serializers.ValidationError({"expiry_date": "Batch expiry date must be strictly after manufacturing date."})

        start = attrs.get('planned_start_date') or (self.instance.planned_start_date if self.instance else None)
        end = attrs.get('planned_end_date') or (self.instance.planned_end_date if self.instance else None)
        if start and end and end < start:
            raise serializers.ValidationError({"planned_end_date": "Planned end date cannot be earlier than planned start date."})
        return attrs

    class Meta:
        model = ProductionOrder
        fields = '__all__'
