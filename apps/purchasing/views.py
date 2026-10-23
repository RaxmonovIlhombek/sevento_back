from drf_spectacular.utils import extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.currency import selectors as currency_selectors
from core.api.idempotency import idempotent_call
from core.api.mixins import CapabilityViewSetMixin
from core.api.schema import ERROR_RESPONSE

from . import selectors, services
from .filters import PurchaseFilter
from .models import ExpenseType, Purchase, Supplier
from .serializers import (
    CancelSerializer,
    CostPreviewSerializer,
    ExpenseTypeSerializer,
    PurchaseDetailSerializer,
    PurchaseListSerializer,
    PurchaseWriteSerializer,
    SupplierSerializer,
)

VIEW, MANAGE = "purchasing.view", "purchasing.manage"


@extend_schema(tags=["purchasing"])
class SupplierViewSet(
    CapabilityViewSetMixin,
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    mixins.ListModelMixin,
    viewsets.GenericViewSet,
):
    queryset = Supplier.objects.none()
    serializer_class = SupplierSerializer
    capability_map = {"list": VIEW, "retrieve": VIEW, "create": MANAGE, "update": MANAGE}
    filterset_fields = ["is_active"]
    search_fields = ["name", "phone", "contact_person", "tin"]
    ordering_fields = ["name", "created_at"]
    ordering = ["name"]

    def get_queryset(self):
        return selectors.suppliers_queryset()

    def perform_create(self, serializer):
        supplier = services.save_supplier(actor=self.request.user, **serializer.validated_data)
        serializer.instance = selectors.suppliers_queryset().get(pk=supplier.pk)

    def perform_update(self, serializer):
        supplier = services.save_supplier(
            actor=self.request.user, supplier=serializer.instance, **serializer.validated_data
        )
        serializer.instance = selectors.suppliers_queryset().get(pk=supplier.pk)


@extend_schema(tags=["purchasing"])
class ExpenseTypeViewSet(
    CapabilityViewSetMixin,
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
    mixins.ListModelMixin,
    viewsets.GenericViewSet,
):
    queryset = ExpenseType.objects.none()
    serializer_class = ExpenseTypeSerializer
    capability_map = {"list": VIEW, "create": MANAGE, "update": MANAGE}
    pagination_class = None
    ordering = ["name"]

    def get_queryset(self):
        return selectors.expense_types_queryset()

    def perform_create(self, serializer):
        serializer.instance = services.save_expense_type(
            actor=self.request.user, **serializer.validated_data
        )

    def perform_update(self, serializer):
        serializer.instance = services.save_expense_type(
            actor=self.request.user, expense_type=serializer.instance, **serializer.validated_data
        )


@extend_schema(tags=["purchasing"])
class PurchaseViewSet(
    CapabilityViewSetMixin,
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    mixins.ListModelMixin,
    viewsets.GenericViewSet,
):
    """Kirimlar. Qoralama → receive (partiyalar, tannarx) → cancel (chiqim bo'lmagan bo'lsa)."""

    queryset = Purchase.objects.none()
    serializer_class = PurchaseListSerializer
    capability_map = {
        "list": VIEW,
        "retrieve": VIEW,
        "preview": VIEW,
        "create": MANAGE,
        "update": MANAGE,
        "receive": MANAGE,
        "cancel": MANAGE,
    }
    filterset_class = PurchaseFilter
    ordering_fields = ["created_at", "received_at", "number", "total_base"]
    ordering = ["-created_at", "-id"]
    http_method_names = ["get", "post", "put", "patch", "head", "options"]

    def get_queryset(self):
        if self.action == "list":
            return selectors.purchases_queryset(self.request.user)
        return selectors.purchase_detail_queryset(self.request.user)

    def _detail(self, purchase_id: int) -> dict:
        purchase = selectors.purchase_detail_queryset(self.request.user).get(pk=purchase_id)
        purchase.can_cancel = services.can_cancel(purchase)
        purchase.base_currency = currency_selectors.base_currency_code()
        return PurchaseDetailSerializer(purchase).data

    @extend_schema(responses=PurchaseDetailSerializer)
    def retrieve(self, request, *args, **kwargs):
        return Response(self._detail(self.get_object().pk))

    @extend_schema(request=PurchaseWriteSerializer, responses={201: PurchaseDetailSerializer})
    def create(self, request, *args, **kwargs):
        serializer = PurchaseWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        purchase = services.create_purchase(actor=request.user, **serializer.validated_data)
        return Response(self._detail(purchase.pk), status=status.HTTP_201_CREATED)

    @extend_schema(request=PurchaseWriteSerializer, responses=PurchaseDetailSerializer)
    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        purchase = self.get_object()
        serializer = PurchaseWriteSerializer(data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        services.update_purchase(
            actor=request.user,
            purchase=purchase,
            items=data.pop("items", None),
            expenses=data.pop("expenses", None) if "expenses" in request.data else None,
            **data,
        )
        return Response(self._detail(purchase.pk))

    @extend_schema(request=None, responses={200: CostPreviewSerializer, 409: ERROR_RESPONSE})
    @action(detail=True, methods=["get"])
    def preview(self, request, pk=None):
        """Qoralama uchun tannarx hisob-kitobi joriy kurs bilan (saqlanmaydi). Kurs yo'q → 409."""
        purchase = self.get_object()
        return Response(CostPreviewSerializer(services.preview_costs(purchase)).data)

    @extend_schema(request=None, responses={200: PurchaseDetailSerializer, 409: ERROR_RESPONSE})
    @action(detail=True, methods=["post"])
    def receive(self, request, pk=None):
        purchase = self.get_object()

        def handler():
            services.receive_purchase(actor=request.user, purchase=purchase)
            return Response(self._detail(purchase.pk))

        return idempotent_call(request, handler)

    @extend_schema(
        request=CancelSerializer, responses={200: PurchaseDetailSerializer, 409: ERROR_RESPONSE}
    )
    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        purchase = self.get_object()
        serializer = CancelSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.cancel_purchase(
            actor=request.user, purchase=purchase, reason=serializer.validated_data["reason"]
        )
        return Response(self._detail(purchase.pk))
