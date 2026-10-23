from decimal import Decimal

from django.utils import timezone
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.branches import selectors as branch_selectors
from apps.currency import selectors as currency_selectors

from .models import (
    Cashbox,
    CashFlowCategory,
    CashShift,
    CashShiftBalance,
    CashTransaction,
    Customer,
    CustomerLedgerEntry,
    Debt,
    DebtAllocation,
    Payment,
    PaymentMethod,
)
from .providers import provider_choices
from .types import Direction


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
        fields = ["id", "code", "name", "direction", "is_manual"]


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
            "shift",
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


# --- mijozlar ---


class CurrencyAmountSerializer(serializers.Serializer):
    currency = serializers.CharField()
    amount = serializers.DecimalField(max_digits=20, decimal_places=4)


_MONEY_FIELD = serializers.DecimalField(max_digits=20, decimal_places=4)


def _money(value) -> str:
    """SerializerMethodField Decimal ni float qilib yubormasin — DecimalField formati (satr)."""
    return _MONEY_FIELD.to_representation(value)


class CustomerSerializer(serializers.ModelSerializer):
    """Ro'yxat: qarz qoldig'i valyuta kesimida va asosiy valyutada (joriy kurs bilan)."""

    balances = serializers.SerializerMethodField()
    debt_base = serializers.SerializerMethodField()
    has_overdue = serializers.SerializerMethodField()
    effective_credit_limit = serializers.SerializerMethodField()

    class Meta:
        model = Customer
        fields = [
            "id",
            "name",
            "phone",
            "tin",
            "address",
            "note",
            "credit_limit_base",
            "default_due_days",
            "effective_credit_limit",
            "is_active",
            "balances",
            "debt_base",
            "has_overdue",
            "created_at",
        ]
        read_only_fields = fields

    def _info(self, customer) -> dict:
        return self.context.get("info", {}).get(customer.pk, {})

    @extend_schema_field(CurrencyAmountSerializer(many=True))
    def get_balances(self, customer) -> list[dict]:
        rows = sorted(self._info(customer).get("balances", {}).items())
        return CurrencyAmountSerializer(
            [{"currency": code, "amount": amount} for code, amount in rows], many=True
        ).data

    @extend_schema_field(serializers.DecimalField(max_digits=20, decimal_places=4))
    def get_debt_base(self, customer) -> str:
        return _money(self._info(customer).get("debt_base", Decimal(0)))

    def get_has_overdue(self, customer) -> bool:
        return self._info(customer).get("overdue", False)

    @extend_schema_field(serializers.DecimalField(max_digits=20, decimal_places=4))
    def get_effective_credit_limit(self, customer) -> str:
        return _money(self._info(customer).get("limit_base", Decimal(0)))


class CustomerWriteSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=150)
    phone = serializers.CharField(max_length=30, required=False, allow_blank=True, default="")
    tin = serializers.CharField(max_length=20, required=False, allow_blank=True, default="")
    address = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")
    note = serializers.CharField(required=False, allow_blank=True, default="")
    credit_limit_base = serializers.DecimalField(
        max_digits=20, decimal_places=4, min_value=Decimal(0), required=False, allow_null=True
    )
    default_due_days = serializers.IntegerField(
        min_value=0, max_value=3650, required=False, allow_null=True
    )
    is_active = serializers.BooleanField(required=False, default=True)


class DebtSerializer(serializers.ModelSerializer):
    customer_name = serializers.CharField(source="customer.name", read_only=True)
    customer_phone = serializers.CharField(source="customer.phone", read_only=True)
    branch_name = serializers.CharField(source="branch.name", read_only=True)
    currency_code = serializers.CharField(source="currency.code", read_only=True)
    currency_decimal_places = serializers.IntegerField(
        source="currency.decimal_places", read_only=True
    )
    remaining = serializers.DecimalField(max_digits=20, decimal_places=4, read_only=True)
    is_overdue = serializers.SerializerMethodField()
    days_overdue = serializers.SerializerMethodField()

    class Meta:
        model = Debt
        fields = [
            "id",
            "customer",
            "customer_name",
            "customer_phone",
            "branch",
            "branch_name",
            "currency",
            "currency_code",
            "currency_decimal_places",
            "amount",
            "paid_amount",
            "returned_amount",
            "remaining",
            "due_date",
            "status",
            "is_overdue",
            "days_overdue",
            "document_type",
            "document_id",
            "document_number",
            "created_at",
            "settled_at",
        ]
        read_only_fields = fields

    def get_is_overdue(self, debt) -> bool:
        return debt.status == Debt.Status.OPEN and debt.due_date < timezone.localdate()

    def get_days_overdue(self, debt) -> int:
        if not self.get_is_overdue(debt):
            return 0
        return (timezone.localdate() - debt.due_date).days


class CreditStatusSerializer(serializers.Serializer):
    limit_base = serializers.DecimalField(max_digits=20, decimal_places=4)
    used_base = serializers.DecimalField(max_digits=20, decimal_places=4)
    available_base = serializers.DecimalField(max_digits=20, decimal_places=4)
    base_currency = serializers.CharField()
    warning_percent = serializers.DecimalField(max_digits=6, decimal_places=2)
    due_days = serializers.IntegerField()


class CustomerDetailSerializer(CustomerSerializer):
    credit = serializers.SerializerMethodField()
    open_debts = serializers.SerializerMethodField()

    class Meta(CustomerSerializer.Meta):
        fields = CustomerSerializer.Meta.fields + ["credit", "open_debts"]
        read_only_fields = fields

    @extend_schema_field(CreditStatusSerializer)
    def get_credit(self, customer) -> dict:
        return CreditStatusSerializer(self.context["credit"]).data

    @extend_schema_field(DebtSerializer(many=True))
    def get_open_debts(self, customer) -> list[dict]:
        return DebtSerializer(self.context["open_debts"], many=True).data


class PayoffSerializer(serializers.Serializer):
    currency = serializers.CharField()
    amount = serializers.DecimalField(max_digits=20, decimal_places=4)


class LedgerEntrySerializer(serializers.ModelSerializer):
    currency_code = serializers.CharField(source="currency.code", read_only=True)
    currency_decimal_places = serializers.IntegerField(
        source="currency.decimal_places", read_only=True
    )
    payment_number = serializers.CharField(
        source="payment.number", read_only=True, default=None, allow_null=True
    )
    method_name = serializers.CharField(
        source="payment.method.name", read_only=True, default=None, allow_null=True
    )
    created_by_name = serializers.CharField(source="created_by.full_name", read_only=True)

    class Meta:
        model = CustomerLedgerEntry
        fields = [
            "id",
            "type",
            "currency_code",
            "currency_decimal_places",
            "amount",
            "balance_after",
            "debt",
            "payment",
            "payment_number",
            "method_name",
            "document_type",
            "document_id",
            "document_number",
            "created_by_name",
            "created_at",
        ]
        read_only_fields = fields


class DebtPaymentWriteSerializer(serializers.Serializer):
    branch = serializers.PrimaryKeyRelatedField(queryset=branch_selectors.active_branches())
    method = serializers.PrimaryKeyRelatedField(
        queryset=PaymentMethod.objects.filter(is_active=True)
    )
    currency = serializers.PrimaryKeyRelatedField(queryset=currency_selectors.active_currencies())
    amount = serializers.DecimalField(max_digits=20, decimal_places=4, min_value=Decimal("0.0001"))
    debt_ids = serializers.ListField(
        child=serializers.IntegerField(), required=False, allow_empty=True, default=list
    )
    note = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")


# --- to'lovlar jurnali ---


class AllocationSerializer(serializers.ModelSerializer):
    currency_code = serializers.CharField(source="debt.currency.code", read_only=True)
    document_number = serializers.CharField(source="debt.document_number", read_only=True)
    document_id = serializers.IntegerField(source="debt.document_id", read_only=True)

    class Meta:
        model = DebtAllocation
        fields = [
            "debt",
            "amount",
            "payment_amount",
            "currency_code",
            "document_id",
            "document_number",
        ]
        read_only_fields = fields


class PaymentListSerializer(PaymentSerializer):
    branch_name = serializers.CharField(source="branch.name", read_only=True)
    currency_decimal_places = serializers.IntegerField(
        source="currency.decimal_places", read_only=True
    )
    customer_name = serializers.CharField(
        source="customer.name", read_only=True, default=None, allow_null=True
    )
    reversal_of_number = serializers.CharField(
        source="reversal_of.number", read_only=True, default=None, allow_null=True
    )

    class Meta(PaymentSerializer.Meta):
        fields = PaymentSerializer.Meta.fields + [
            "branch",
            "branch_name",
            "currency_decimal_places",
            "customer",
            "customer_name",
            "document_type",
            "document_id",
            "document_number",
            "reversal_of_number",
            "note",
        ]
        read_only_fields = fields


class PaymentDetailSerializer(PaymentListSerializer):
    allocations = AllocationSerializer(many=True, read_only=True)
    can_refund = serializers.SerializerMethodField()

    class Meta(PaymentListSerializer.Meta):
        fields = PaymentListSerializer.Meta.fields + ["allocations", "can_refund"]
        read_only_fields = fields

    def get_can_refund(self, payment) -> bool:
        return (
            payment.kind == "payment"
            and payment.document_type == "customer"
            and payment.status == Payment.Status.COMPLETED
            and self.context.get("can_refund", False)
        )


class ReasonSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=255)


# --- smena va qo'lda yozuv ---


class ShiftBalanceSerializer(serializers.ModelSerializer):
    currency_code = serializers.CharField(source="cashbox.currency.code", read_only=True)
    currency_decimal_places = serializers.IntegerField(
        source="cashbox.currency.decimal_places", read_only=True
    )
    current_balance = serializers.DecimalField(
        source="cashbox.balance", max_digits=20, decimal_places=4, read_only=True
    )

    class Meta:
        model = CashShiftBalance
        fields = [
            "cashbox",
            "currency_code",
            "currency_decimal_places",
            "opening_balance",
            "current_balance",
            "expected_balance",
            "actual_balance",
            "difference",
        ]
        read_only_fields = fields


class CashShiftSerializer(serializers.ModelSerializer):
    branch_name = serializers.CharField(source="branch.name", read_only=True)
    opened_by_name = serializers.CharField(source="opened_by.full_name", read_only=True)
    closed_by_name = serializers.CharField(
        source="closed_by.full_name", read_only=True, default=None, allow_null=True
    )
    balances = ShiftBalanceSerializer(many=True, read_only=True)

    class Meta:
        model = CashShift
        fields = [
            "id",
            "branch",
            "branch_name",
            "status",
            "opened_by_name",
            "opened_at",
            "closed_by_name",
            "closed_at",
            "note",
            "balances",
        ]
        read_only_fields = fields


class CurrentShiftSerializer(serializers.Serializer):
    shift = CashShiftSerializer(allow_null=True)


class ShiftOpenSerializer(serializers.Serializer):
    branch = serializers.PrimaryKeyRelatedField(queryset=branch_selectors.active_branches())
    note = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")


class ShiftActualSerializer(serializers.Serializer):
    currency = serializers.PrimaryKeyRelatedField(queryset=currency_selectors.active_currencies())
    amount = serializers.DecimalField(max_digits=20, decimal_places=4, min_value=Decimal(0))


class ShiftCloseSerializer(serializers.Serializer):
    actual = ShiftActualSerializer(many=True)
    note = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")


class CashEntryWriteSerializer(serializers.Serializer):
    branch = serializers.PrimaryKeyRelatedField(queryset=branch_selectors.active_branches())
    currency = serializers.PrimaryKeyRelatedField(queryset=currency_selectors.active_currencies())
    direction = serializers.ChoiceField(choices=Direction.choices)
    category = serializers.SlugRelatedField(
        slug_field="code", queryset=CashFlowCategory.objects.filter(is_manual=True)
    )
    amount = serializers.DecimalField(max_digits=20, decimal_places=4, min_value=Decimal("0.0001"))
    note = serializers.CharField(max_length=255)
