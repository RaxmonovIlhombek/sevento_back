from rest_framework import serializers

from .models import Cashbox, CashFlowCategory, CashTransaction, Payment, PaymentMethod
from .providers import provider_choices


class PaymentMethodSerializer(serializers.ModelSerializer):
    provider = serializers.ChoiceField(choices=provider_choices(), default="manual")

    class Meta:
        model = PaymentMethod
        fields = ["id", "code", "name", "provider", "is_cash", "is_active", "sort_order"]
        extra_kwargs = {"code": {"validators": []}}

    def validate_code(self, value):
        value = value.strip().lower()
        qs = PaymentMethod.objects.filter(code=value)
        if self.instance is not None:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("Bu kod band", code="unique")
        return value


class CashFlowCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = CashFlowCategory
        fields = ["id", "code", "name", "direction"]


class CashboxSerializer(serializers.ModelSerializer):
    branch_name = serializers.CharField(source="branch.name", read_only=True)
    currency_code = serializers.CharField(source="currency.code", read_only=True)
    currency_decimal_places = serializers.IntegerField(
        source="currency.decimal_places", read_only=True
    )

    class Meta:
        model = Cashbox
        fields = [
            "id",
            "name",
            "branch",
            "branch_name",
            "currency",
            "currency_code",
            "currency_decimal_places",
            "balance",
            "is_active",
            "updated_at",
        ]
        read_only_fields = fields


class CashTransactionSerializer(serializers.ModelSerializer):
    cashbox_name = serializers.CharField(source="cashbox.name", read_only=True)
    branch = serializers.IntegerField(source="cashbox.branch_id", read_only=True)
    currency_code = serializers.CharField(source="cashbox.currency.code", read_only=True)
    category_code = serializers.CharField(source="category.code", read_only=True)
    category_name = serializers.CharField(source="category.name", read_only=True)
    payment_number = serializers.CharField(
        source="payment.number", read_only=True, default=None, allow_null=True
    )
    created_by_name = serializers.CharField(source="created_by.full_name", read_only=True)

    class Meta:
        model = CashTransaction
        fields = [
            "id",
            "cashbox",
            "cashbox_name",
            "branch",
            "currency_code",
            "direction",
            "category_code",
            "category_name",
            "amount",
            "balance_after",
            "payment_number",
            "document_type",
            "document_id",
            "document_number",
            "note",
            "created_by_name",
            "created_at",
        ]
        read_only_fields = fields


class PaymentSerializer(serializers.ModelSerializer):
    """Hujjat ichida ko'rsatish uchun (savdo tafsiloti, chek)."""

    method_code = serializers.CharField(source="method.code", read_only=True)
    method_name = serializers.CharField(source="method.name", read_only=True)
    is_cash = serializers.BooleanField(source="method.is_cash", read_only=True)
    currency_code = serializers.CharField(source="currency.code", read_only=True)
    received_by_name = serializers.CharField(source="received_by.full_name", read_only=True)

    class Meta:
        model = Payment
        fields = [
            "id",
            "number",
            "kind",
            "direction",
            "status",
            "method",
            "method_code",
            "method_name",
            "is_cash",
            "currency",
            "currency_code",
            "amount",
            "rate_to_base",
            "amount_base",
            "received_by_name",
            "received_at",
        ]
        read_only_fields = fields
