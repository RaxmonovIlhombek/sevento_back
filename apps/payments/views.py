from decimal import Decimal

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from apps.currency import selectors as currency_selectors
from apps.currency.selectors import RateUnavailable
from core import settings_service
from core.access import ensure_branch_access
from core.api.idempotency import idempotent_call
from core.api.mixins import CapabilityViewSetMixin
from core.api.schema import ERROR_RESPONSE

from . import selectors, services
from .filters import (
    CashboxFilter,
    CashShiftFilter,
    CashTransactionFilter,
    CustomerFilter,
    DebtFilter,
    PaymentFilter,
)
from .models import (
    Cashbox,
    CashFlowCategory,
    CashShift,
    CashTransaction,
    Customer,
    Debt,
    Payment,
    PaymentMethod,
)
from .serializers import (
    CashboxSerializer,
    CashEntryWriteSerializer,
    CashFlowCategorySerializer,
    CashShiftSerializer,
    CashTransactionSerializer,
    CurrentShiftSerializer,
    CustomerDetailSerializer,
    CustomerSerializer,
    CustomerWriteSerializer,
    DebtPaymentWriteSerializer,
    DebtSerializer,
    LedgerEntrySerializer,
    PaymentDetailSerializer,
    PaymentListSerializer,
    PaymentMethodSerializer,
    PayoffSerializer,
    ReasonSerializer,
    ShiftCloseSerializer,
    ShiftOpenSerializer,
)

CASHBOX_VIEW = "cashbox.view"


@extend_schema(tags=["payments"])
class PaymentMethodViewSet(
    CapabilityViewSetMixin,
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
    mixins.ListModelMixin,
    viewsets.GenericViewSet,
):
    """To'lov turlari (MB da). Ro'yxat — kassir ham ko'radi; o'zgartirish — sozlamalar huquqi."""

    queryset = PaymentMethod.objects.none()
    serializer_class = PaymentMethodSerializer
    capability_map = {
        "list": ("sales.create", "payments.view", "settings.manage"),
        "create": "settings.manage",
        "update": "settings.manage",
    }
    filterset_fields = ["is_active", "is_cash"]
    pagination_class = None

    def get_queryset(self):
        return selectors.payment_methods_queryset()

    def perform_create(self, serializer):
        serializer.instance = services.save_payment_method(
            actor=self.request.user, **serializer.validated_data
        )

    def perform_update(self, serializer):
        serializer.instance = services.save_payment_method(
            actor=self.request.user, method=serializer.instance, **serializer.validated_data
        )


@extend_schema(tags=["payments"])
class CashFlowCategoryViewSet(
    CapabilityViewSetMixin, mixins.ListModelMixin, viewsets.GenericViewSet
):
    queryset = CashFlowCategory.objects.none()
    serializer_class = CashFlowCategorySerializer
    capability_map = {"list": CASHBOX_VIEW}
    pagination_class = None

    def get_queryset(self):
        return selectors.cash_categories_queryset()


@extend_schema(tags=["payments"])
class CashboxViewSet(
    CapabilityViewSetMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    """Kassalar (nuqta × valyuta) va qoldiq. Faqat ko'rinadigan nuqtalar."""

    queryset = Cashbox.objects.none()
    serializer_class = CashboxSerializer
    capability_map = {"list": CASHBOX_VIEW, "retrieve": CASHBOX_VIEW}
    filterset_class = CashboxFilter
    pagination_class = None

    def get_queryset(self):
        return selectors.cashboxes_queryset(self.request.user)


@extend_schema(tags=["payments"])
class CashTransactionViewSet(
    CapabilityViewSetMixin, mixins.ListModelMixin, viewsets.GenericViewSet
):
    """Kassa jurnali. POST — qo'lda kirim/chiqim (kiritish, inkassatsiya, xarajat)."""

    queryset = CashTransaction.objects.none()
    serializer_class = CashTransactionSerializer
    capability_map = {"list": CASHBOX_VIEW, "create": "cashbox.manage"}
    filterset_class = CashTransactionFilter
    ordering = ["-created_at", "-id"]

    def get_queryset(self):
        return selectors.cash_transactions_queryset(self.request.user)

    @extend_schema(
        request=CashEntryWriteSerializer,
        responses={201: CashTransactionSerializer, 400: ERROR_RESPONSE, 409: ERROR_RESPONSE},
    )
    def create(self, request, *args, **kwargs):
        serializer = CashEntryWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        tx = services.manual_entry(actor=request.user, **serializer.validated_data)
        return Response(
            CashTransactionSerializer(self.get_queryset().get(pk=tx.pk)).data,
            status=status.HTTP_201_CREATED,
        )


# --- mijozlar ---


def _customer_info(customers) -> dict[int, dict]:
    """Sahifadagi mijozlar uchun qarz qoldig'i (valyuta kesimida va asosiy valyutada) va limit."""
    ids = [c.pk for c in customers]
    balances = selectors.customer_balances(ids)
    overdue = selectors.overdue_customer_ids(ids)
    rates: dict[str, Decimal] = {}

    def to_base(code: str, amount: Decimal) -> Decimal:
        if code not in rates:
            try:
                rates[code] = currency_selectors.rate_to_base(code)
            except RateUnavailable:
                rates[code] = Decimal(0)
        return amount * rates[code]

    info = {}
    for c in customers:
        bal = balances.get(c.pk, {})
        info[c.pk] = {
            "balances": bal,
            "debt_base": sum((to_base(k, v) for k, v in bal.items()), Decimal(0)).quantize(
                Decimal("0.0001")
            ),
            "overdue": c.pk in overdue,
            "limit_base": services.credit_limit_base(c),
        }
    return info


@extend_schema(tags=["payments"])
class CustomerViewSet(
    CapabilityViewSetMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    """Mijozlar (barcha nuqtalar uchun umumiy). Kredit limitini — alohida huquq bilan."""

    queryset = Customer.objects.none()
    serializer_class = CustomerSerializer
    capability_map = {
        "list": "customers.view",
        "retrieve": "customers.view",
        "ledger": "customers.view",
        "payoff": "customers.view",
        "create": "customers.manage",
        "update": "customers.manage",
        "pay": "payments.receive",
    }
    filterset_class = CustomerFilter
    ordering_fields = ["name", "created_at"]
    ordering = ["name", "id"]

    def get_queryset(self):
        return selectors.customers_queryset()

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        rows = list(page if page is not None else queryset)
        data = CustomerSerializer(rows, many=True, context={"info": _customer_info(rows)}).data
        return self.get_paginated_response(data) if page is not None else Response(data)

    def _detail(self, customer) -> dict:
        status_ = services.credit_status(customer)
        credit = {
            "limit_base": status_.limit_base,
            "used_base": status_.used_base,
            "available_base": status_.available_base,
            "base_currency": currency_selectors.base_currency_code(),
            "warning_percent": settings_service.get("payments.credit_limit_warning_percent"),
            "due_days": services.due_days(customer),
        }
        open_debts = selectors.customer_debts(customer.pk).filter(status=Debt.Status.OPEN)
        context = {"info": _customer_info([customer]), "credit": credit, "open_debts": open_debts}
        return CustomerDetailSerializer(customer, context=context).data

    @extend_schema(responses=CustomerDetailSerializer)
    def retrieve(self, request, *args, **kwargs):
        return Response(self._detail(self.get_object()))

    @extend_schema(request=CustomerWriteSerializer, responses={201: CustomerDetailSerializer})
    def create(self, request, *args, **kwargs):
        serializer = CustomerWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        customer = services.save_customer(actor=request.user, **serializer.validated_data)
        return Response(self._detail(customer), status=status.HTTP_201_CREATED)

    @extend_schema(request=CustomerWriteSerializer, responses=CustomerDetailSerializer)
    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        customer = self.get_object()
        serializer = CustomerWriteSerializer(data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        customer = services.save_customer(
            actor=request.user, customer=customer, **serializer.validated_data
        )
        return Response(self._detail(customer))

    @extend_schema(responses=LedgerEntrySerializer(many=True))
    @action(detail=True, methods=["get"])
    def ledger(self, request, pk=None):
        """Mijoz hisobi (akt-sverka): nasiya +, to'lov −, qoldiq valyuta kesimida."""
        customer = self.get_object()
        queryset = selectors.ledger_queryset(customer.pk)
        currency = request.query_params.get("currency")
        if currency:
            queryset = queryset.filter(currency__code__iexact=currency)
        page = self.paginate_queryset(queryset)
        data = LedgerEntrySerializer(page, many=True).data
        return self.get_paginated_response(data)

    @extend_schema(
        parameters=[
            OpenApiParameter("currency", OpenApiTypes.STR, required=True),
            OpenApiParameter("debt_ids", OpenApiTypes.STR, required=False, description="1,2,3"),
        ],
        responses=PayoffSerializer,
    )
    @action(detail=True, methods=["get"], pagination_class=None)
    def payoff(self, request, pk=None):
        """Qarzni shu valyutada to'liq yopish summasi (joriy kurs, yuqoriga yaxlitlangan)."""
        customer = self.get_object()
        code = request.query_params.get("currency", "").upper()
        currency = currency_selectors.get_currency(code)
        if currency is None:
            raise ValidationError({"currency": "Noma'lum valyuta"})
        raw_ids = request.query_params.get("debt_ids", "")
        ids = [int(x) for x in raw_ids.split(",") if x.strip().isdigit()]
        amount = services.payoff_amount(customer, currency, ids or None)
        return Response(PayoffSerializer({"currency": code, "amount": amount}).data)

    @extend_schema(
        request=DebtPaymentWriteSerializer,
        responses={201: PaymentDetailSerializer, 400: ERROR_RESPONSE, 409: ERROR_RESPONSE},
    )
    @action(detail=True, methods=["post"])
    def pay(self, request, pk=None):
        """Qarz to'lovi (Idempotency-Key): eng eski muddatdan boshlab yopiladi."""
        customer = self.get_object()
        serializer = DebtPaymentWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        def handler():
            payment = services.receive_debt_payment(
                actor=request.user, customer=customer, **serializer.validated_data
            )
            detail = selectors.payments_queryset(request.user).get(pk=payment.pk)
            context = {"can_refund": request.user.has_capability("payments.refund")}
            return Response(
                PaymentDetailSerializer(detail, context=context).data,
                status=status.HTTP_201_CREATED,
            )

        return idempotent_call(request, handler)


@extend_schema(tags=["payments"])
class DebtViewSet(
    CapabilityViewSetMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    """Qarzlar (nuqta bo'yicha). ?overdue=true — muddati o'tganlar."""

    queryset = Debt.objects.none()
    serializer_class = DebtSerializer
    capability_map = {"list": "debts.view", "retrieve": "debts.view"}
    filterset_class = DebtFilter
    ordering_fields = ["due_date", "created_at", "amount"]
    ordering = ["due_date", "id"]

    def get_queryset(self):
        return selectors.debts_queryset(self.request.user)


@extend_schema(tags=["payments"])
class PaymentViewSet(
    CapabilityViewSetMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    """To'lovlar jurnali (savdo to'lovlari, qaytimlar, qarz to'lovlari, qaytarishlar)."""

    queryset = Payment.objects.none()
    serializer_class = PaymentListSerializer
    capability_map = {
        "list": "payments.view",
        "retrieve": "payments.view",
        "refund": "payments.refund",
    }
    filterset_class = PaymentFilter
    ordering = ["-received_at", "-id"]

    def get_queryset(self):
        qs = selectors.payments_queryset(self.request.user)
        if self.action != "list":
            qs = qs.prefetch_related("allocations__debt__currency")
        return qs

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["can_refund"] = self.request.user.has_capability("payments.refund")
        return context

    @extend_schema(responses=PaymentDetailSerializer)
    def retrieve(self, request, *args, **kwargs):
        return Response(
            PaymentDetailSerializer(self.get_object(), context=self.get_serializer_context()).data
        )

    @extend_schema(
        request=ReasonSerializer, responses={200: PaymentDetailSerializer, 409: ERROR_RESPONSE}
    )
    @action(detail=True, methods=["post"])
    def refund(self, request, pk=None):
        """Qarz to'lovini qaytarish: qarz qayta ochiladi, naqd kassadan chiqadi."""
        payment = self.get_object()
        serializer = ReasonSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.refund_debt_payment(
            actor=request.user, payment=payment, reason=serializer.validated_data["reason"]
        )
        fresh = self.get_queryset().get(pk=payment.pk)
        return Response(PaymentDetailSerializer(fresh, context=self.get_serializer_context()).data)


@extend_schema(tags=["payments"])
class CashShiftViewSet(
    CapabilityViewSetMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    """Kassa smenalari: ochish (qoldiq qotiriladi), yopish (sanalgan naqd, farq yoziladi)."""

    queryset = CashShift.objects.none()
    serializer_class = CashShiftSerializer
    capability_map = {
        "list": CASHBOX_VIEW,
        "retrieve": CASHBOX_VIEW,
        "current": CASHBOX_VIEW,
        "open": "cashbox.manage",
        "close": "cashbox.manage",
    }
    filterset_class = CashShiftFilter
    ordering = ["-opened_at", "-id"]

    def get_queryset(self):
        return selectors.shifts_queryset(self.request.user)

    @extend_schema(
        parameters=[OpenApiParameter("branch", OpenApiTypes.INT, required=True)],
        responses=CurrentShiftSerializer,
    )
    @action(detail=False, methods=["get"], pagination_class=None)
    def current(self, request):
        """Nuqtadagi ochiq smena (yo'q bo'lsa null)."""
        branch = request.query_params.get("branch", "")
        if not branch.isdigit():
            raise ValidationError({"branch": "Nuqta majburiy"})
        ensure_branch_access(request.user, int(branch))
        shift = selectors.current_shift(int(branch))
        return Response({"shift": CashShiftSerializer(shift).data if shift else None})

    @extend_schema(
        request=ShiftOpenSerializer, responses={201: CashShiftSerializer, 409: ERROR_RESPONSE}
    )
    @action(detail=False, methods=["post"])
    def open(self, request):
        serializer = ShiftOpenSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        shift = services.open_shift(actor=request.user, **serializer.validated_data)
        return Response(
            CashShiftSerializer(self.get_queryset().get(pk=shift.pk)).data,
            status=status.HTTP_201_CREATED,
        )

    @extend_schema(
        request=ShiftCloseSerializer, responses={200: CashShiftSerializer, 409: ERROR_RESPONSE}
    )
    @action(detail=True, methods=["post"])
    def close(self, request, pk=None):
        shift = self.get_object()
        serializer = ShiftCloseSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        services.close_shift(
            actor=request.user,
            shift=shift,
            actual={row["currency"].pk: row["amount"] for row in data["actual"]},
            note=data["note"],
        )
        return Response(CashShiftSerializer(self.get_queryset().get(pk=shift.pk)).data)
