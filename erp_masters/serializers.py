from rest_framework import serializers
from .models import (
    UnitOfMeasure, UOMConversion, Warehouse, StorageBin,
    ItemMaster, SupplierMaster, CustomerMaster,
    QualitySpecification, SpecificationParameter,
    BOMHeader, BOMLine
)


class UnitOfMeasureSerializer(serializers.ModelSerializer):
    class Meta:
        model = UnitOfMeasure
        fields = '__all__'


class UOMConversionSerializer(serializers.ModelSerializer):
    from_uom_code = serializers.CharField(source='from_uom.code', read_only=True)
    to_uom_code = serializers.CharField(source='to_uom.code', read_only=True)

    class Meta:
        model = UOMConversion
        fields = '__all__'


class StorageBinSerializer(serializers.ModelSerializer):
    class Meta:
        model = StorageBin
        fields = '__all__'


class WarehouseSerializer(serializers.ModelSerializer):
    branch_name = serializers.CharField(source='branch.name', read_only=True)
    bins = StorageBinSerializer(many=True, read_only=True)

    class Meta:
        model = Warehouse
        fields = '__all__'


class ItemMasterSerializer(serializers.ModelSerializer):
    base_uom_code = serializers.CharField(source='base_uom.code', read_only=True)
    item_type_display = serializers.CharField(source='get_item_type_display', read_only=True)

    class Meta:
        model = ItemMaster
        fields = '__all__'


class SupplierMasterSerializer(serializers.ModelSerializer):
    class Meta:
        model = SupplierMaster
        fields = '__all__'
        extra_kwargs = {
            'bank_account_no': {'write_only': True}  # Sensitive bank data protected
        }


class CustomerMasterSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomerMaster
        fields = '__all__'


class SpecificationParameterSerializer(serializers.ModelSerializer):
    class Meta:
        model = SpecificationParameter
        fields = '__all__'


class QualitySpecificationSerializer(serializers.ModelSerializer):
    item_name = serializers.CharField(source='item.name', read_only=True)
    item_code = serializers.CharField(source='item.item_code', read_only=True)
    parameters = SpecificationParameterSerializer(many=True, read_only=True)

    class Meta:
        model = QualitySpecification
        fields = '__all__'


class BOMLineSerializer(serializers.ModelSerializer):
    component_name = serializers.CharField(source='component.name', read_only=True)
    component_code = serializers.CharField(source='component.item_code', read_only=True)
    uom_code = serializers.CharField(source='uom.code', read_only=True)

    class Meta:
        model = BOMLine
        fields = '__all__'


class BOMHeaderSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source='product.name', read_only=True)
    product_code = serializers.CharField(source='product.item_code', read_only=True)
    batch_uom_code = serializers.CharField(source='batch_uom.code', read_only=True)
    lines = BOMLineSerializer(many=True, read_only=True)

    class Meta:
        model = BOMHeader
        fields = '__all__'
