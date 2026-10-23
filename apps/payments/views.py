from drf_spectacular.utils import extend_schema
from rest_framework import mixins, viewsets

from core.api.mixins import CapabilityViewSetMixin

from . import selectors, services
from .filters import CashboxFilter, CashTransactionFilter
from .models import Cashbox, CashFlowCategory, CashTransaction, PaymentMethod
from .serializers import (
    CashboxSerializer,
    CashFlowCategorySerializer,
    CashTransactionSerializer,
    PaymentMethodSerializer,
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
    """Kassa jurnali (faqat o'qish)."""

    queryset = CashTransaction.objects.none()
    serializer_class = CashTransactionSerializer
    capability_map = {"list": CASHBOX_VIEW}
    filterset_class = CashTransactionFilter
    ordering = ["-created_at", "-id"]

    def get_queryset(self):
        return selectors.cash_transactions_queryset(self.request.user)
