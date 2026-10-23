from decimal import Decimal

from rest_framework import serializers

from apps.branches import selectors as branch_selectors
from apps.catalog import selectors as catalog_selectors
from apps.currency import selectors as currency_selectors

from .models import AllocationMethod, ExpenseType, Purchase, PurchaseExpense, PurchaseItem, Supplier


class SupplierSerializer(serializers.ModelSerializer):
    purchases_count = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = Supplier
        fields = [
            "id",
            "name",
            "phone",
            "contact_person",
            "tin",
            "address",
            "note",
            "is_active",
            "purchases_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at"]


class ExpenseTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = ExpenseType
        fields = [
            "id",
            "code",
            "name",
            "default_allocation",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at"]
        extra_kwargs = {"code": {"validators": []}}

    def validate_code(self, value):
        value = value.strip().lower()
        qs = ExpenseType.objects.filter(code=value)
        if self.instance is not None:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("Bu kod band", code="unique")
        return value


# --- kirim: o'qish ---


class PurchaseItemSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.name", read_only=True)
    product_sku = serializers.CharField(source="product.sku", read_only=True)
    unit_code = serializers.CharField(source="product.unit.code", read_only=True)
    unit_decimal_places = serializers.IntegerField(
        source="product.unit.decimal_places", read_only=True
    )

    class Meta:
        model = PurchaseItem
        fields = [
            "id",
            "product",
            "product_name",
            "product_sku",
            "unit_code",
            "unit_decimal_places",
            "quantity",
            "unit_price",
            "line_total",
            "line_total_base",
            "allocated_expense_base",
            "landed_unit_cost_base",
        ]
        read_only_fields = fields


class PurchaseExpenseSerializer(serializers.ModelSerializer):
    expense_type_name = serializers.CharField(source="expense_type.name", read_only=True)
    currency_code = serializers.CharField(source="currency.code", read_only=True)

    class Meta:
        model = PurchaseExpense
        fields = [
            "id",
            "expense_type",
            "expense_type_name",
            "currency",
            "currency_code",
            "amount",
            "allocation_method",
            "rate_to_base",
            "amount_base",
            "note",
        ]
        read_only_fields = fields


class PurchaseListSerializer(serializers.ModelSerializer):
    branch_name = serializers.CharField(source="branch.name", read_only=True)
    supplier_name = serializers.CharField(source="supplier.name", read_only=True)
    currency_code = serializers.CharField(source="currency.code", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    items_count = serializers.IntegerField(read_only=True, default=0)
    created_by_name = serializers.CharField(
        source="created_by.full_name", read_only=True, default=None, allow_null=True
    )

    class Meta:
        model = Purchase
        fields = [
            "id",
            "number",
            "branch",
            "branch_name",
            "supplier",
            "supplier_name",
            "status",
            "status_display",
            "invoice_number",
            "invoice_date",
            "currency",
            "currency_code",
            "subtotal",
            "total_base",
            "items_count",
            "created_by_name",
            "created_at",
            "received_at",
        ]
        read_only_fields = fields


class CostPreviewLineSerializer(serializers.Serializer):
    line_total = serializers.DecimalField(max_digits=20, decimal_places=4)
    line_total_base = serializers.DecimalField(max_digits=20, decimal_places=4)
    allocated_expense_base = serializers.DecimalField(max_digits=20, decimal_places=4)
    landed_unit_cost_base = serializers.DecimalField(max_digits=20, decimal_places=6)


class CostPreviewSerializer(serializers.Serializer):
    rate_to_base = serializers.DecimalField(max_digits=24, decimal_places=12)
    subtotal = serializers.DecimalField(max_digits=20, decimal_places=4)
    subtotal_base = serializers.DecimalField(max_digits=20, decimal_places=4)
    expenses_total_base = serializers.DecimalField(max_digits=20, decimal_places=4)
    total_base = serializers.DecimalField(max_digits=20, decimal_places=4)
    lines = CostPreviewLineSerializer(many=True)


class PurchaseDetailSerializer(PurchaseListSerializer):
    items = PurchaseItemSerializer(many=True, read_only=True)
    expenses = PurchaseExpenseSerializer(many=True, read_only=True)
    received_by_name = serializers.CharField(
        source="received_by.full_name", read_only=True, default=None, allow_null=True
    )
    cancelled_by_name = serializers.CharField(
        source="cancelled_by.full_name", read_only=True, default=None, allow_null=True
    )
    can_cancel = serializers.BooleanField(read_only=True, default=False)
    base_currency = serializers.CharField(read_only=True, default="")

    class Meta(PurchaseListSerializer.Meta):
        fields = PurchaseListSerializer.Meta.fields + [
            "rate_to_base",
            "subtotal_base",
            "expenses_total_base",
            "note",
            "items",
            "expenses",
            "received_by_name",
            "cancelled_by_name",
            "cancelled_at",
            "cancel_reason",
            "can_cancel",
            "base_currency",
        ]
        read_only_fields = fields


# --- kirim: yozish ---


class PurchaseItemWriteSerializer(serializers.Serializer):
    product = serializers.PrimaryKeyRelatedField(queryset=catalog_selectors.products_queryset())
    quantity = serializers.DecimalField(max_digits=14, decimal_places=3, min_value=Decimal("0.001"))
    unit_price = serializers.DecimalField(max_digits=20, decimal_places=4, min_value=0)


class PurchaseExpenseWriteSerializer(serializers.Serializer):
    expense_type = serializers.PrimaryKeyRelatedField(
        queryset=ExpenseType.objects.filter(is_active=True)
    )
    currency = serializers.PrimaryKeyRelatedField(queryset=currency_selectors.active_currencies())
    amount = serializers.DecimalField(max_digits=20, decimal_places=4, min_value=Decimal("0.0001"))
    allocation_method = serializers.ChoiceField(choices=AllocationMethod.choices, required=False)
    note = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")


class PurchaseWriteSerializer(serializers.Serializer):
    branch = serializers.PrimaryKeyRelatedField(queryset=branch_selectors.active_branches())
    supplier = serializers.PrimaryKeyRelatedField(queryset=Supplier.objects.filter(is_active=True))
    currency = serializers.PrimaryKeyRelatedField(queryset=currency_selectors.active_currencies())
    invoice_number = serializers.CharField(
        max_length=50, required=False, allow_blank=True, default=""
    )
    invoice_date = serializers.DateField(required=False, allow_null=True, default=None)
    note = serializers.CharField(required=False, allow_blank=True, default="")
    items = PurchaseItemWriteSerializer(many=True)
    expenses = PurchaseExpenseWriteSerializer(many=True, required=False, default=list)


class CancelSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=255)
