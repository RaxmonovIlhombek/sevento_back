from decimal import Decimal

from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.branches import selectors as branch_selectors
from apps.catalog import selectors as catalog_selectors

from .models import (
    Batch,
    StockCount,
    StockCountItem,
    StockLevel,
    StockMovement,
    Transfer,
    TransferItem,
    WriteOff,
    WriteOffItem,
    WriteOffReason,
)

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


# --- 7-bosqich: hujjat qatorlari uchun umumiy ---


class _ProductLineMixin(serializers.Serializer):
    product_name = serializers.CharField(source="product.name", read_only=True)
    product_sku = serializers.CharField(source="product.sku", read_only=True)
    product_barcode = serializers.CharField(source="product.barcode", read_only=True)
    unit_code = serializers.CharField(source="product.unit.code", read_only=True)
    unit_decimal_places = serializers.IntegerField(
        source="product.unit.decimal_places", read_only=True
    )


PRODUCT_LINE_FIELDS = [
    "product",
    "product_name",
    "product_sku",
    "product_barcode",
    "unit_code",
    "unit_decimal_places",
]


class LineWriteSerializer(serializers.Serializer):
    product = serializers.PrimaryKeyRelatedField(queryset=catalog_selectors.products_queryset())
    quantity = serializers.DecimalField(max_digits=14, decimal_places=3, min_value=Decimal("0.001"))


class InventoryCancelSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=255)


class BranchBriefSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    code = serializers.CharField()
    name = serializers.CharField()


class DocumentRefSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    number = serializers.CharField()


# --- ko'chirish ---


class TransferItemSerializer(_HideCostMixin, _ProductLineMixin, serializers.ModelSerializer):
    cost_fields = ("unit_cost_base", "total_cost_base")

    shortage = serializers.DecimalField(max_digits=14, decimal_places=3, read_only=True)

    class Meta:
        model = TransferItem
        fields = [
            "id",
            *PRODUCT_LINE_FIELDS,
            "quantity",
            "quantity_received",
            "shortage",
            "unit_cost_base",
            "total_cost_base",
        ]
        read_only_fields = fields


class TransferListSerializer(_HideCostMixin, serializers.ModelSerializer):
    cost_fields = ("total_cost_base", "shortage_cost_base")

    from_branch_name = serializers.CharField(source="from_branch.name", read_only=True)
    to_branch_name = serializers.CharField(source="to_branch.name", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    items_count = serializers.IntegerField(read_only=True, default=0)
    created_by_name = serializers.CharField(
        source="created_by.full_name", read_only=True, default=None, allow_null=True
    )
    total_cost_base = serializers.DecimalField(
        max_digits=20, decimal_places=4, read_only=True, required=False
    )
    shortage_cost_base = serializers.DecimalField(
        max_digits=20, decimal_places=4, read_only=True, required=False
    )

    class Meta:
        model = Transfer
        fields = [
            "id",
            "number",
            "from_branch",
            "from_branch_name",
            "to_branch",
            "to_branch_name",
            "status",
            "status_display",
            "items_count",
            "has_discrepancy",
            "total_cost_base",
            "shortage_cost_base",
            "note",
            "created_by_name",
            "created_at",
            "sent_at",
            "received_at",
        ]
        read_only_fields = fields


class TransferPermissionsSerializer(serializers.Serializer):
    edit = serializers.BooleanField()
    send = serializers.BooleanField()
    receive = serializers.BooleanField()
    cancel = serializers.BooleanField()


class TransferDetailSerializer(TransferListSerializer):
    items = TransferItemSerializer(many=True, read_only=True)
    sent_by_name = serializers.CharField(
        source="sent_by.full_name", read_only=True, default=None, allow_null=True
    )
    received_by_name = serializers.CharField(
        source="received_by.full_name", read_only=True, default=None, allow_null=True
    )
    cancelled_by_name = serializers.CharField(
        source="cancelled_by.full_name", read_only=True, default=None, allow_null=True
    )
    shortage_write_off = serializers.SerializerMethodField()
    allowed = TransferPermissionsSerializer(read_only=True)

    class Meta(TransferListSerializer.Meta):
        fields = TransferListSerializer.Meta.fields + [
            "items",
            "sent_by_name",
            "received_by_name",
            "receive_note",
            "cancelled_by_name",
            "cancelled_at",
            "cancel_reason",
            "shortage_write_off",
            "allowed",
        ]
        read_only_fields = fields

    @extend_schema_field(DocumentRefSerializer(allow_null=True))
    def get_shortage_write_off(self, obj):
        write_off = next(iter(obj.write_offs.all()), None)
        return {"id": write_off.pk, "number": write_off.number} if write_off else None


class TransferWriteSerializer(serializers.Serializer):
    from_branch = serializers.PrimaryKeyRelatedField(queryset=branch_selectors.active_branches())
    to_branch = serializers.PrimaryKeyRelatedField(queryset=branch_selectors.all_branches())
    note = serializers.CharField(required=False, allow_blank=True, default="")
    items = LineWriteSerializer(many=True)


class TransferReceiveLineSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    quantity_received = serializers.DecimalField(max_digits=14, decimal_places=3, min_value=0)


class TransferReceiveSerializer(serializers.Serializer):
    """Berilmagan qatorlar to'liq qabul qilingan hisoblanadi."""

    items = TransferReceiveLineSerializer(many=True, required=False, default=list)
    note = serializers.CharField(required=False, allow_blank=True, default="")


# --- inventarizatsiya ---


class StockCountListSerializer(_HideCostMixin, serializers.ModelSerializer):
    cost_fields = ("surplus_cost_base", "shortage_cost_base")

    branch_name = serializers.CharField(source="branch.name", read_only=True)
    category_name = serializers.CharField(
        source="category.name", read_only=True, default=None, allow_null=True
    )
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    items_count = serializers.IntegerField(read_only=True, default=0)
    counted_count = serializers.IntegerField(read_only=True, default=0)
    created_by_name = serializers.CharField(
        source="created_by.full_name", read_only=True, default=None, allow_null=True
    )
    completed_by_name = serializers.CharField(
        source="completed_by.full_name", read_only=True, default=None, allow_null=True
    )
    surplus_cost_base = serializers.DecimalField(
        max_digits=20, decimal_places=4, read_only=True, required=False
    )
    shortage_cost_base = serializers.DecimalField(
        max_digits=20, decimal_places=4, read_only=True, required=False
    )

    class Meta:
        model = StockCount
        fields = [
            "id",
            "number",
            "branch",
            "branch_name",
            "category",
            "category_name",
            "status",
            "status_display",
            "items_count",
            "counted_count",
            "surplus_cost_base",
            "shortage_cost_base",
            "note",
            "created_by_name",
            "created_at",
            "completed_by_name",
            "completed_at",
        ]
        read_only_fields = fields


class StockCountItemSerializer(_HideCostMixin, _ProductLineMixin, serializers.ModelSerializer):
    cost_fields = ("unit_cost_base", "cost_difference_base")

    category_name = serializers.CharField(
        source="product.category.name", read_only=True, default=None, allow_null=True
    )
    # qoralamada — hozirgi qoldiq (yakunlashda shu bilan solishtiriladi)
    current_quantity = serializers.DecimalField(
        max_digits=14, decimal_places=3, read_only=True, default=None, allow_null=True
    )

    class Meta:
        model = StockCountItem
        fields = [
            "id",
            *PRODUCT_LINE_FIELDS,
            "category_name",
            "expected_quantity",
            "current_quantity",
            "counted_quantity",
            "difference",
            "unit_cost_base",
            "cost_difference_base",
        ]
        read_only_fields = fields


class StockCountCreateSerializer(serializers.Serializer):
    branch = serializers.PrimaryKeyRelatedField(queryset=branch_selectors.active_branches())
    category = serializers.PrimaryKeyRelatedField(
        queryset=catalog_selectors.categories_queryset(), required=False, allow_null=True
    )
    include_zero = serializers.BooleanField(required=False, default=False)
    note = serializers.CharField(required=False, allow_blank=True, default="")


class CountedLineSerializer(serializers.Serializer):
    product = serializers.PrimaryKeyRelatedField(queryset=catalog_selectors.products_queryset())
    counted_quantity = serializers.DecimalField(
        max_digits=14, decimal_places=3, min_value=0, allow_null=True
    )


class CountedWriteSerializer(serializers.Serializer):
    items = CountedLineSerializer(many=True, allow_empty=False)


# --- hisobdan chiqarish ---


class WriteOffReasonSerializer(serializers.ModelSerializer):
    class Meta:
        model = WriteOffReason
        fields = ["id", "code", "name", "is_active", "is_system", "created_at", "updated_at"]
        read_only_fields = ["is_system", "created_at", "updated_at"]
        extra_kwargs = {"code": {"validators": []}}

    def validate_code(self, value):
        value = value.strip().lower()
        qs = WriteOffReason.objects.filter(code=value)
        if self.instance is not None:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("Bu kod band", code="unique")
        return value


class WriteOffItemSerializer(_HideCostMixin, _ProductLineMixin, serializers.ModelSerializer):
    cost_fields = ("unit_cost_base", "total_cost_base")

    class Meta:
        model = WriteOffItem
        fields = ["id", *PRODUCT_LINE_FIELDS, "quantity", "unit_cost_base", "total_cost_base"]
        read_only_fields = fields


class WriteOffListSerializer(_HideCostMixin, serializers.ModelSerializer):
    cost_fields = ("total_cost_base",)

    branch_name = serializers.CharField(source="branch.name", read_only=True)
    reason_code = serializers.CharField(source="reason.code", read_only=True)
    reason_name = serializers.CharField(source="reason.name", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    items_count = serializers.IntegerField(read_only=True, default=0)
    transfer_number = serializers.CharField(
        source="transfer.number", read_only=True, default=None, allow_null=True
    )
    created_by_name = serializers.CharField(
        source="created_by.full_name", read_only=True, default=None, allow_null=True
    )
    total_cost_base = serializers.DecimalField(
        max_digits=20, decimal_places=4, read_only=True, required=False
    )

    class Meta:
        model = WriteOff
        fields = [
            "id",
            "number",
            "branch",
            "branch_name",
            "reason",
            "reason_code",
            "reason_name",
            "status",
            "status_display",
            "items_count",
            "total_cost_base",
            "transfer",
            "transfer_number",
            "note",
            "created_by_name",
            "completed_at",
        ]
        read_only_fields = fields


class WriteOffDetailSerializer(WriteOffListSerializer):
    items = WriteOffItemSerializer(many=True, read_only=True)
    cancelled_by_name = serializers.CharField(
        source="cancelled_by.full_name", read_only=True, default=None, allow_null=True
    )
    can_cancel = serializers.BooleanField(read_only=True, default=False)

    class Meta(WriteOffListSerializer.Meta):
        fields = WriteOffListSerializer.Meta.fields + [
            "items",
            "cancelled_by_name",
            "cancelled_at",
            "cancel_reason",
            "can_cancel",
        ]
        read_only_fields = fields


class WriteOffWriteSerializer(serializers.Serializer):
    branch = serializers.PrimaryKeyRelatedField(queryset=branch_selectors.active_branches())
    reason = serializers.PrimaryKeyRelatedField(queryset=WriteOffReason.objects.all())
    note = serializers.CharField(required=False, allow_blank=True, default="")
    items = LineWriteSerializer(many=True)
