from rest_framework import serializers

from .models import Batch, StockLevel, StockMovement

COST_FIELDS_STOCK = ("value_base",)
COST_FIELDS_MOVEMENT = ("unit_cost_base", "total_cost_base")


class _HideCostMixin:
    """inventory.view_cost huquqi bo'lmasa tannarx maydonlari javobdan olib tashlanadi."""

    cost_fields: tuple[str, ...] = ()

    def to_representation(self, instance):
        data = super().to_representation(instance)
        request = self.context.get("request")
        if request is not None and not request.user.has_capability("inventory.view_cost"):
            for field in self.cost_fields:
                data.pop(field, None)
        return data


class StockLevelSerializer(_HideCostMixin, serializers.ModelSerializer):
    cost_fields = COST_FIELDS_STOCK

    branch_name = serializers.CharField(source="branch.name", read_only=True)
    product_name = serializers.CharField(source="product.name", read_only=True)
    product_sku = serializers.CharField(source="product.sku", read_only=True)
    product_barcode = serializers.CharField(source="product.barcode", read_only=True)
    category_name = serializers.CharField(
        source="product.category.name", read_only=True, default=None, allow_null=True
    )
    unit_code = serializers.CharField(source="product.unit.code", read_only=True)
    unit_decimal_places = serializers.IntegerField(
        source="product.unit.decimal_places", read_only=True
    )
    effective_min = serializers.DecimalField(max_digits=14, decimal_places=3, read_only=True)
    is_below_min = serializers.BooleanField(read_only=True)
    value_base = serializers.DecimalField(
        max_digits=24, decimal_places=4, read_only=True, required=False
    )

    class Meta:
        model = StockLevel
        fields = [
            "id",
            "branch",
            "branch_name",
            "product",
            "product_name",
            "product_sku",
            "product_barcode",
            "category_name",
            "unit_code",
            "unit_decimal_places",
            "quantity",
            "min_quantity",
            "effective_min",
            "is_below_min",
            "value_base",
            "updated_at",
        ]
        read_only_fields = fields


class MinQuantitySerializer(serializers.Serializer):
    min_quantity = serializers.DecimalField(
        max_digits=14, decimal_places=3, min_value=0, allow_null=True
    )


class BatchSerializer(serializers.ModelSerializer):
    branch_name = serializers.CharField(source="branch.name", read_only=True)
    product_name = serializers.CharField(source="product.name", read_only=True)
    unit_code = serializers.CharField(source="product.unit.code", read_only=True)

    class Meta:
        model = Batch
        fields = [
            "id",
            "branch",
            "branch_name",
            "product",
            "product_name",
            "unit_code",
            "source_type",
            "source_id",
            "source_number",
            "received_at",
            "quantity_initial",
            "quantity_remaining",
            "unit_cost_base",
        ]
        read_only_fields = fields


class StockMovementSerializer(_HideCostMixin, serializers.ModelSerializer):
    cost_fields = COST_FIELDS_MOVEMENT

    branch_name = serializers.CharField(source="branch.name", read_only=True)
    product_name = serializers.CharField(source="product.name", read_only=True)
    product_sku = serializers.CharField(source="product.sku", read_only=True)
    unit_code = serializers.CharField(source="product.unit.code", read_only=True)
    type_display = serializers.CharField(source="get_type_display", read_only=True)
    created_by_name = serializers.CharField(
        source="created_by.full_name", read_only=True, default=None, allow_null=True
    )
    unit_cost_base = serializers.DecimalField(
        max_digits=20, decimal_places=6, read_only=True, required=False
    )
    total_cost_base = serializers.DecimalField(
        max_digits=20, decimal_places=4, read_only=True, required=False
    )

    class Meta:
        model = StockMovement
        fields = [
            "id",
            "branch",
            "branch_name",
            "product",
            "product_name",
            "product_sku",
            "unit_code",
            "batch",
            "type",
            "type_display",
            "quantity",
            "balance_after",
            "unit_cost_base",
            "total_cost_base",
            "document_type",
            "document_id",
            "document_number",
            "created_by",
            "created_by_name",
            "created_at",
        ]
        read_only_fields = fields
