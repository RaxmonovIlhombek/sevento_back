from django.http import HttpResponse
from django.utils.dateparse import parse_date
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.catalog import selectors as catalog_selectors
from apps.currency import selectors as currency_selectors
from core import settings_service
from core.access import ensure_branch_access
from core.api.idempotency import idempotent_call
from core.api.mixins import CapabilityViewSetMixin
from core.api.schema import ERROR_RESPONSE

from . import selectors, services
from .filters import SaleFilter, SaleReturnFilter
from .models import Sale, SaleReturn
from .receipt import render_receipt_pdf
from .serializers import (
    DailySummarySerializer,
    PosConfigSerializer,
    PosProductSerializer,
    PosQuerySerializer,
    SaleCancelSerializer,
    SaleDetailSerializer,
    SaleListSerializer,
    SaleReturnDetailSerializer,
    SaleReturnListSerializer,
    SaleReturnWriteSerializer,
    SaleWriteSerializer,
)

VIEW, CREATE = "sales.view", "sales.create"


@extend_schema(tags=["sales"])
class SaleViewSet(
    CapabilityViewSetMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    """Savdolar. POST — bitta so'rovda yakunlangan savdo (Idempotency-Key bilan)."""

    queryset = Sale.objects.none()
    serializer_class = SaleListSerializer
    capability_map = {
        "list": VIEW,
        "retrieve": VIEW,
        "receipt": VIEW,
        "summary": VIEW,
        "create": CREATE,
        "pos_products": CREATE,
        "pos_config": CREATE,
        "cancel": "sales.cancel",
    }
    filterset_class = SaleFilter
    ordering_fields = ["completed_at", "number", "total", "total_base"]
    ordering = ["-completed_at", "-id"]

    def get_queryset(self):
        if self.action == "list":
            return selectors.sales_queryset(self.request.user)
        return selectors.sale_detail_queryset(self.request.user)

    def get_serializer_context(self):
        context = super().get_serializer_context()
        user = self.request.user
        context["can_view_cost"] = user.has_capability("inventory.view_cost")
        context["can_cancel"] = user.has_capability("sales.cancel")
        context["can_return"] = lambda sale: services.can_return_sale(user, sale)
        return context

    def _detail(self, sale_id: int) -> dict:
        sale = selectors.sale_detail_queryset(self.request.user).get(pk=sale_id)
        return SaleDetailSerializer(sale, context=self.get_serializer_context()).data

    @extend_schema(responses=SaleDetailSerializer)
    def retrieve(self, request, *args, **kwargs):
        return Response(self._detail(self.get_object().pk))

    @extend_schema(
        request=SaleWriteSerializer,
        responses={201: SaleDetailSerializer, 400: ERROR_RESPONSE, 409: ERROR_RESPONSE},
    )
    def create(self, request, *args, **kwargs):
        serializer = SaleWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        def handler():
            sale = services.create_sale(actor=request.user, **serializer.validated_data)
            return Response(self._detail(sale.pk), status=status.HTTP_201_CREATED)

        return idempotent_call(request, handler)

    @extend_schema(
        request=SaleCancelSerializer, responses={200: SaleDetailSerializer, 409: ERROR_RESPONSE}
    )
    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        sale = self.get_object()
        serializer = SaleCancelSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.cancel_sale(
            actor=request.user, sale=sale, reason=serializer.validated_data["reason"]
        )
        return Response(self._detail(sale.pk))

    @extend_schema(responses={(200, "application/pdf"): OpenApiTypes.BINARY})
    @action(detail=True, methods=["get"])
    def receipt(self, request, pk=None):
        """Chek PDF (80 mm). O'zbek harflari bilan, termoprinter uchun."""
        sale = self.get_object()
        pdf = render_receipt_pdf(sale, selectors.sale_payments(sale))
        response = HttpResponse(pdf, content_type="application/pdf")
        response["Content-Disposition"] = f'inline; filename="chek-{sale.number}.pdf"'
        return response

    @extend_schema(
        parameters=[PosQuerySerializer],
        responses=PosProductSerializer(many=True),
    )
    @action(detail=False, methods=["get"], url_path="pos-products", pagination_class=None)
    def pos_products(self, request):
        """Kassa qidiruvi: nomi/artikul/shtrix-kod, savdo valyutasidagi narx va nuqta qoldig'i."""
        query = PosQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        data = query.validated_data
        ensure_branch_access(request.user, data["branch"].pk)
        price_type = data.get("price_type") or catalog_selectors.default_price_type()
        rows = selectors.pos_products(
            branch_id=data["branch"].pk,
            currency=data["currency"],
            price_type=price_type,
            search=data["search"],
            barcode=data["barcode"],
            ids=data["ids"],
            limit=max(data["limit"], len(data["ids"])),
        )
        return Response(PosProductSerializer(rows, many=True).data)

    @extend_schema(responses=PosConfigSerializer)
    @action(detail=False, methods=["get"], url_path="pos-config", pagination_class=None)
    def pos_config(self, request):
        """Kassa sozlamalari: boshlang'ich valyuta, foydalanuvchining chegirma chegarasi."""
        user = request.user
        if user.has_capability("sales.discount.unlimited"):
            limit = None
        elif user.has_capability("sales.discount"):
            limit = settings_service.get("sales.max_seller_discount_percent")
        else:
            limit = 0
        data = {
            "default_currency": settings_service.get("sales.default_currency"),
            "max_discount_percent": limit,
        }
        return Response(PosConfigSerializer(data).data)

    @extend_schema(
        parameters=[
            OpenApiParameter("date", OpenApiTypes.DATE, required=False),
            OpenApiParameter("branch", OpenApiTypes.INT, required=False),
        ],
        responses=DailySummarySerializer,
    )
    @action(detail=False, methods=["get"], pagination_class=None)
    def summary(self, request):
        """Kunlik savdo xulosasi (dashboard). Tannarx/foyda — faqat inventory.view_cost bilan."""
        on = parse_date(request.query_params.get("date", "") or "") or None
        branch = request.query_params.get("branch")
        data = selectors.daily_summary(
            request.user, on=on, branch_id=int(branch) if branch and branch.isdigit() else None
        )
        data["base_currency"] = currency_selectors.base_currency_code()
        if not request.user.has_capability("inventory.view_cost"):
            data["cost_base"] = None
            data["profit_base"] = None
        return Response(DailySummarySerializer(data).data)


@extend_schema(tags=["sales"])
class SaleReturnViewSet(
    CapabilityViewSetMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    """Qaytarishlar. POST — tovar omborga, summa qarzdan ayiriladi, qolgani mijozga qaytariladi."""

    queryset = SaleReturn.objects.none()
    serializer_class = SaleReturnListSerializer
    capability_map = {"list": VIEW, "retrieve": VIEW, "create": "sales.returns.create"}
    filterset_class = SaleReturnFilter
    ordering_fields = ["created_at", "number", "total"]
    ordering = ["-created_at", "-id"]

    def get_queryset(self):
        if self.action == "list":
            return selectors.returns_queryset(self.request.user)
        return selectors.return_detail_queryset(self.request.user)

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["can_view_cost"] = self.request.user.has_capability("inventory.view_cost")
        return context

    def _detail(self, return_id: int) -> dict:
        row = selectors.return_detail_queryset(self.request.user).get(pk=return_id)
        return SaleReturnDetailSerializer(row, context=self.get_serializer_context()).data

    @extend_schema(responses=SaleReturnDetailSerializer)
    def retrieve(self, request, *args, **kwargs):
        return Response(self._detail(self.get_object().pk))

    @extend_schema(
        request=SaleReturnWriteSerializer,
        responses={201: SaleReturnDetailSerializer, 400: ERROR_RESPONSE, 409: ERROR_RESPONSE},
    )
    def create(self, request, *args, **kwargs):
        serializer = SaleReturnWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        def handler():
            sale_return = services.create_return(actor=request.user, **serializer.validated_data)
            return Response(self._detail(sale_return.pk), status=status.HTTP_201_CREATED)

        return idempotent_call(request, handler)
