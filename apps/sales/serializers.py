from decimal import Decimal

from django.utils import timezone
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.branches import selectors as branch_selectors
from apps.catalog import selectors as catalog_selectors
from apps.currency import selectors as currency_selectors
from apps.payments import selectors as payment_selectors

from .models import Sale, SaleItem, SaleReturn, SaleReturnItem

COST_FIELDS = ("cost_base", "profit_base")


class _HideCostMixin:
    """Tannarx va foyda faqat `inventory.view_cost` huquqi borlarga (sotuvchiga — yo'q)."""

    def to_representation(self, instance):
        data = super().to_representation(instance)
        if not self.context.get("can_view_cost", False):
            for field in COST_FIELDS:
                if field in data:
                    data[field] = None
        return data


class SaleListSerializer(_HideCostMixin, serializers.ModelSerializer):
    branch_name = serializers.CharField(source="branch.name", read_only=True)
    seller_name = serializers.CharField(source="seller.full_name", read_only=True)
    currency_code = serializers.CharField(source="currency.code", read_only=True)
    currency_decimal_places = serializers.IntegerField(
        source="currency.decimal_places", read_only=True
    )
    customer_name = serializers.CharField(
        source="customer.name", read_only=True, default=None, allow_null=True
    )
    items_count = serializers.IntegerField(read_only=True)
    cost_base = serializers.DecimalField(
        max_digits=20, decimal_places=4, read_only=True, allow_null=True
    )
    profit_base = serializers.DecimalField(
        max_digits=20, decimal_places=4, read_only=True, allow_null=True
    )
    return_state = serializers.ChoiceField(
        choices=[("none", "none"), ("partial", "partial"), ("full", "full")], read_only=True
    )

    class Meta:
        model = Sale
        fields = [
            "id",
            "number",
            "status",
            "branch",
            "branch_name",
            "seller",
            "seller_name",
            "currency",
            "currency_code",
            "currency_decimal_places",
            "subtotal",
            "discount_total",
            "total",
            "total_base",
            "cost_base",
            "profit_base",
            "paid_total",
            "change_amount",
            "customer",
            "customer_name",
            "debt_amount",
            "due_date",
            "returned_total",
            "return_state",
            "items_count",
            "completed_at",
            "cancelled_at",
        ]
        read_only_fields = fields


class SaleItemSerializer(_HideCostMixin, serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.name", read_only=True)
    product_sku = serializers.CharField(source="product.sku", read_only=True)
    unit_code = serializers.CharField(source="product.unit.code", read_only=True)
    unit_decimal_places = serializers.IntegerField(
        source="product.unit.decimal_places", read_only=True
    )
    cost_base = serializers.DecimalField(
        max_digits=20, decimal_places=4, read_only=True, allow_null=True
    )

    class Meta:
        model = SaleItem
        fields = [
            "id",
            "position",
            "product",
            "product_name",
            "product_sku",
            "unit_code",
            "unit_decimal_places",
            "quantity",
            "unit_price",
            "discount_amount",
            "line_total",
            "cost_base",
            "returned_quantity",
        ]
        read_only_fields = fields


class SalePaymentSerializer(serializers.Serializer):
    """Savdo to'lovlari (payments app dagi Payment, atribut nomlari bo'yicha)."""

    id = serializers.IntegerField()
    number = serializers.CharField()
    kind = serializers.CharField()
    direction = serializers.CharField()
    status = serializers.CharField()
    method_code = serializers.CharField(source="method.code")
    method_name = serializers.CharField(source="method.name")
    is_cash = serializers.BooleanField(source="method.is_cash")
    currency_code = serializers.CharField(source="currency.code")
    currency_decimal_places = serializers.IntegerField(source="currency.decimal_places")
    amount = serializers.DecimalField(max_digits=20, decimal_places=4)
    received_by_name = serializers.CharField(source="received_by.full_name")
    received_at = serializers.DateTimeField()


class SaleDebtSerializer(serializers.Serializer):
    """Savdo nasiyasining hozirgi holati (payments.Debt)."""

    id = serializers.IntegerField()
    amount = serializers.DecimalField(max_digits=20, decimal_places=4)
    paid_amount = serializers.DecimalField(max_digits=20, decimal_places=4)
    returned_amount = serializers.DecimalField(max_digits=20, decimal_places=4)
    remaining = serializers.DecimalField(max_digits=20, decimal_places=4)
    due_date = serializers.DateField()
    status = serializers.CharField()


class SaleReturnBriefSerializer(serializers.ModelSerializer):
    refund_method_name = serializers.CharField(
        source="refund_method.name", read_only=True, default=None, allow_null=True
    )
    created_by_name = serializers.CharField(source="created_by.full_name", read_only=True)

    class Meta:
        model = SaleReturn
        fields = [
            "id",
            "number",
            "total",
            "debt_reduction",
            "refund_amount",
            "refund_method_name",
            "reason",
            "created_by_name",
            "created_at",
        ]
        read_only_fields = fields


class SaleDetailSerializer(SaleListSerializer):
    price_type_name = serializers.CharField(source="price_type.name", read_only=True)
    cancelled_by_name = serializers.CharField(
        source="cancelled_by.full_name", read_only=True, default=None, allow_null=True
    )
    items = serializers.SerializerMethodField()
    payments = serializers.SerializerMethodField()
    base_currency = serializers.SerializerMethodField()
    can_cancel = serializers.SerializerMethodField()
    can_return = serializers.SerializerMethodField()
    debt = serializers.SerializerMethodField()
    returns = SaleReturnBriefSerializer(many=True, read_only=True)

    class Meta(SaleListSerializer.Meta):
        fields = SaleListSerializer.Meta.fields + [
            "price_type",
            "price_type_name",
            "rate_to_base",
            "note",
            "cancelled_by_name",
            "cancel_reason",
            "items",
            "payments",
            "base_currency",
            "can_cancel",
            "can_return",
            "debt",
            "returned_total_base",
            "returns",
        ]
        read_only_fields = fields

    @extend_schema_field(SaleItemSerializer(many=True))
    def get_items(self, sale) -> list[dict]:
        return SaleItemSerializer(sale.items.all(), many=True, context=self.context).data

    @extend_schema_field(SalePaymentSerializer(many=True))
    def get_payments(self, sale) -> list[dict]:
        rows = payment_selectors.payments_for_document("sale", sale.pk)
        return SalePaymentSerializer(rows, many=True).data

    def get_base_currency(self, sale) -> str:
        return currency_selectors.base_currency_code()

    @extend_schema_field(SaleDebtSerializer(allow_null=True))
    def get_debt(self, sale) -> dict | None:
        debt = payment_selectors.document_debt("sale", sale.pk) if sale.debt_amount else None
        return SaleDebtSerializer(debt).data if debt else None

    def get_can_cancel(self, sale) -> bool:
        # qaytarish bo'lgan savdo bekor qilinmaydi (qolganini qaytarish orqali)
        return (
            sale.status == Sale.Status.COMPLETED
            and self.context.get("can_cancel", False)
            and not sale.returns.all()
        )

    def get_can_return(self, sale) -> bool:
        can_return = self.context.get("can_return")
        return (
            sale.status == Sale.Status.COMPLETED
            and can_return is not None
            and can_return(sale)
            and any(i.returned_quantity < i.quantity for i in sale.items.all())
        )


# --- yozish ---


class SaleItemWriteSerializer(serializers.Serializer):
    product = serializers.PrimaryKeyRelatedField(
        queryset=catalog_selectors.products_queryset().select_related("unit")
    )
    quantity = serializers.DecimalField(max_digits=14, decimal_places=3, min_value=Decimal("0.001"))
    discount_amount = serializers.DecimalField(
        max_digits=20, decimal_places=4, min_value=Decimal(0), required=False, default=Decimal(0)
    )


class SalePaymentWriteSerializer(serializers.Serializer):
    method = serializers.PrimaryKeyRelatedField(queryset=payment_selectors.active_payment_methods())
    currency = serializers.PrimaryKeyRelatedField(queryset=currency_selectors.active_currencies())
    amount = serializers.DecimalField(max_digits=20, decimal_places=4, min_value=Decimal("0.0001"))


class SaleWriteSerializer(serializers.Serializer):
    branch = serializers.PrimaryKeyRelatedField(queryset=branch_selectors.active_branches())
    currency = serializers.PrimaryKeyRelatedField(queryset=currency_selectors.active_currencies())
    price_type = serializers.PrimaryKeyRelatedField(
        queryset=catalog_selectors.price_types_queryset(), required=False, allow_null=True
    )
    items = SaleItemWriteSerializer(many=True, allow_empty=False)
    payments = SalePaymentWriteSerializer(many=True, allow_empty=True)
    customer = serializers.PrimaryKeyRelatedField(
        queryset=payment_selectors.customers_queryset().filter(is_active=True),
        required=False,
        allow_null=True,
        help_text="Nasiya uchun majburiy; to'liq to'lovda ixtiyoriy (mijoz tarixi uchun)",
    )
    due_date = serializers.DateField(
        required=False, allow_null=True, help_text="Nasiya muddati; bo'sh — mijoz/sozlama defaulti"
    )
    note = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")
    expected_total = serializers.DecimalField(
        max_digits=20,
        decimal_places=4,
        required=False,
        allow_null=True,
        help_text="Kassada ko'rsatilgan jami; serverdagidan farq qilsa 409 total_mismatch",
    )

    def validate_due_date(self, value):
        if value is not None and value < timezone.localdate():
            raise serializers.ValidationError("Muddat bugundan oldin bo'lmasin", code="past_date")
        return value


class SaleCancelSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=255)


class PosProductSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    sku = serializers.CharField()
    barcode = serializers.CharField()
    name = serializers.CharField()
    unit_code = serializers.CharField()
    unit_decimal_places = serializers.IntegerField()
    price = serializers.DecimalField(max_digits=20, decimal_places=4, allow_null=True)
    stock = serializers.DecimalField(max_digits=14, decimal_places=3)


class PosQuerySerializer(serializers.Serializer):
    branch = serializers.PrimaryKeyRelatedField(queryset=branch_selectors.active_branches())
    currency = serializers.SlugRelatedField(
        slug_field="code", queryset=currency_selectors.active_currencies()
    )
    price_type = serializers.PrimaryKeyRelatedField(
        queryset=catalog_selectors.price_types_queryset(), required=False
    )
    search = serializers.CharField(required=False, allow_blank=True, default="")
    barcode = serializers.CharField(required=False, allow_blank=True, default="")
    ids = serializers.CharField(
        required=False, allow_blank=True, default="", help_text="vergul bilan: 1,2,3"
    )
    limit = serializers.IntegerField(required=False, min_value=1, max_value=100, default=20)

    def validate_ids(self, value: str) -> list[int]:
        try:
            return [int(x) for x in value.split(",") if x.strip()][:100]
        except ValueError:
            raise serializers.ValidationError("Butun sonlar vergul bilan") from None


class PosConfigSerializer(serializers.Serializer):
    default_currency = serializers.CharField()
    max_discount_percent = serializers.DecimalField(
        max_digits=6, decimal_places=2, allow_null=True, help_text="null — cheksiz"
    )


class SummaryCurrencySerializer(serializers.Serializer):
    currency = serializers.CharField()
    count = serializers.IntegerField()
    total = serializers.DecimalField(max_digits=20, decimal_places=4)


class DailySummarySerializer(serializers.Serializer):
    date = serializers.DateField()
    branch = serializers.IntegerField(allow_null=True)
    count = serializers.IntegerField()
    cancelled_count = serializers.IntegerField()
    by_currency = SummaryCurrencySerializer(many=True)
    total_base = serializers.DecimalField(max_digits=20, decimal_places=4)
    cost_base = serializers.DecimalField(max_digits=20, decimal_places=4, allow_null=True)
    returns_count = serializers.IntegerField()
    returns_total_base = serializers.DecimalField(max_digits=20, decimal_places=4)
    profit_base = serializers.DecimalField(max_digits=20, decimal_places=4, allow_null=True)
    base_currency = serializers.CharField()


# --- qaytarish ---


class SaleReturnListSerializer(_HideCostMixin, serializers.ModelSerializer):
    sale_number = serializers.CharField(source="sale.number", read_only=True)
    branch_name = serializers.CharField(source="branch.name", read_only=True)
    customer_name = serializers.CharField(
        source="customer.name", read_only=True, default=None, allow_null=True
    )
    currency_code = serializers.CharField(source="currency.code", read_only=True)
    currency_decimal_places = serializers.IntegerField(
        source="currency.decimal_places", read_only=True
    )
    refund_method_name = serializers.CharField(
        source="refund_method.name", read_only=True, default=None, allow_null=True
    )
    created_by_name = serializers.CharField(source="created_by.full_name", read_only=True)
    items_count = serializers.IntegerField(read_only=True, default=0)
    cost_base = serializers.DecimalField(
        max_digits=20, decimal_places=4, read_only=True, allow_null=True
    )

    class Meta:
        model = SaleReturn
        fields = [
            "id",
            "number",
            "sale",
            "sale_number",
            "branch",
            "branch_name",
            "customer",
            "customer_name",
            "currency_code",
            "currency_decimal_places",
            "total",
            "total_base",
            "cost_base",
            "debt_reduction",
            "refund_amount",
            "refund_method",
            "refund_method_name",
            "reason",
            "items_count",
            "created_by_name",
            "created_at",
        ]
        read_only_fields = fields


class SaleReturnItemSerializer(_HideCostMixin, serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.name", read_only=True)
    unit_code = serializers.CharField(source="product.unit.code", read_only=True)
    unit_decimal_places = serializers.IntegerField(
        source="product.unit.decimal_places", read_only=True
    )
    cost_base = serializers.DecimalField(
        max_digits=20, decimal_places=4, read_only=True, allow_null=True
    )

    class Meta:
        model = SaleReturnItem
        fields = [
            "id",
            "sale_item",
            "product",
            "product_name",
            "unit_code",
            "unit_decimal_places",
            "quantity",
            "amount",
            "cost_base",
        ]
        read_only_fields = fields


class SaleReturnDetailSerializer(SaleReturnListSerializer):
    items = SaleReturnItemSerializer(many=True, read_only=True)

    class Meta(SaleReturnListSerializer.Meta):
        fields = SaleReturnListSerializer.Meta.fields + ["items"]
        read_only_fields = fields


class SaleReturnLineSerializer(serializers.Serializer):
    sale_item = serializers.IntegerField()
    quantity = serializers.DecimalField(max_digits=14, decimal_places=3, min_value=Decimal("0.001"))


class SaleReturnWriteSerializer(serializers.Serializer):
    sale = serializers.PrimaryKeyRelatedField(queryset=Sale.objects.all())
    items = SaleReturnLineSerializer(many=True, allow_empty=False)
    reason = serializers.CharField(max_length=255)
    refund_method = serializers.PrimaryKeyRelatedField(
        queryset=payment_selectors.active_payment_methods(),
        required=False,
        allow_null=True,
        help_text="Pul qaytarish turi; bo'sh — naqd",
    )
