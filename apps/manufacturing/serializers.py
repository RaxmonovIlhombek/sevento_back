from rest_framework import serializers

from .models import BOMItem, BillOfMaterials, ProductionOrder


class BOMItemSerializer(serializers.ModelSerializer):
    component_name = serializers.CharField(source="component.name", read_only=True)

    class Meta:
        model = BOMItem
        fields = ["id", "component", "component_name", "quantity", "unit", "scrap_rate"]


class BillOfMaterialsSerializer(serializers.ModelSerializer):
    items = BOMItemSerializer(many=True, required=False)
    product_name = serializers.CharField(source="product.name", read_only=True)

    class Meta:
        model = BillOfMaterials
        fields = [
            "id",
            "product",
            "product_name",
            "name",
            "version",
            "status",
            "quantity",
            "notes",
            "items",
            "created_at",
            "updated_at",
        ]

    def create(self, validated_data):
        items_data = validated_data.pop("items", [])
        bom = BillOfMaterials.objects.create(**validated_data)
        for it in items_data:
            BOMItem.objects.create(bom=bom, **it)
        return bom

    def update(self, instance, validated_data):
        items_data = validated_data.pop("items", None)
        for attr, val in validated_data.items():
            setattr(instance, attr, val)
        instance.save()
        if items_data is not None:
            instance.items.all().delete()
            for it in items_data:
                BOMItem.objects.create(bom=instance, **it)
        return instance


class ProductionOrderSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.name", read_only=True)
    bom_name = serializers.CharField(source="bom.name", read_only=True)
    branch_name = serializers.CharField(source="branch.name", read_only=True)

    class Meta:
        model = ProductionOrder
        fields = [
            "id",
            "number",
            "product",
            "product_name",
            "bom",
            "bom_name",
            "branch",
            "branch_name",
            "quantity",
            "status",
            "planned_start",
            "planned_end",
            "actual_start",
            "actual_end",
            "created_by",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["number", "status", "actual_start", "actual_end", "created_by"]
