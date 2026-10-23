from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from core.access import ensure_branch_access
from core.api.mixins import CapabilityViewSetMixin

from . import selectors, services
from .filters import ProductFilter
from .models import Category, PriceType, Product, Unit
from .serializers import (
    CategorySerializer,
    CategoryTreeSerializer,
    PriceTypeSerializer,
    ProductPriceSerializer,
    ProductSerializer,
    ProductWriteSerializer,
    SetPriceSerializer,
    UnitSerializer,
)

VIEW, MANAGE = "catalog.view", "catalog.manage"
REF_MAP = {"list": VIEW, "retrieve": VIEW, "create": MANAGE, "update": MANAGE}


@extend_schema(tags=["catalog"])
class CategoryViewSet(
    CapabilityViewSetMixin,
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    mixins.ListModelMixin,
    viewsets.GenericViewSet,
):
    queryset = Category.objects.none()
    serializer_class = CategorySerializer
    capability_map = {**REF_MAP, "tree": VIEW}
    filterset_fields = ["parent", "is_active"]
    search_fields = ["name"]
    ordering = ["sort_order", "name"]
    pagination_class = None

    def get_queryset(self):
        return selectors.categories_queryset()

    def perform_create(self, serializer):
        serializer.instance = services.create_category(
            actor=self.request.user, **serializer.validated_data
        )

    def perform_update(self, serializer):
        serializer.instance = services.update_category(
            actor=self.request.user, category=serializer.instance, **serializer.validated_data
        )

    @extend_schema(
        responses=CategoryTreeSerializer(many=True),
        parameters=[OpenApiParameter("include_inactive", bool, required=False)],
    )
    @action(detail=False, methods=["get"])
    def tree(self, request):
        include_inactive = request.query_params.get("include_inactive", "true") != "false"
        return Response(selectors.category_tree(include_inactive=include_inactive))


@extend_schema(tags=["catalog"])
class UnitViewSet(
    CapabilityViewSetMixin,
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    mixins.ListModelMixin,
    viewsets.GenericViewSet,
):
    queryset = Unit.objects.none()
    serializer_class = UnitSerializer
    capability_map = REF_MAP
    filterset_fields = ["is_active"]
    ordering = ["name"]
    pagination_class = None

    def get_queryset(self):
        return selectors.units_queryset()

    def perform_create(self, serializer):
        serializer.instance = services.save_unit(
            actor=self.request.user, **serializer.validated_data
        )

    def perform_update(self, serializer):
        serializer.instance = services.save_unit(
            actor=self.request.user, unit=serializer.instance, **serializer.validated_data
        )


@extend_schema(tags=["catalog"])
class PriceTypeViewSet(
    CapabilityViewSetMixin,
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    mixins.ListModelMixin,
    viewsets.GenericViewSet,
):
    queryset = PriceType.objects.none()
    serializer_class = PriceTypeSerializer
    capability_map = REF_MAP
    ordering = ["sort_order", "code"]
    pagination_class = None

    def get_queryset(self):
        return selectors.price_types_queryset()

    def perform_create(self, serializer):
        serializer.instance = services.save_price_type(
            actor=self.request.user, **serializer.validated_data
        )

    def perform_update(self, serializer):
        serializer.instance = services.save_price_type(
            actor=self.request.user, price_type=serializer.instance, **serializer.validated_data
        )


@extend_schema(tags=["catalog"])
class ProductViewSet(
    CapabilityViewSetMixin,
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    mixins.ListModelMixin,
    viewsets.GenericViewSet,
):
    """Tovarlar. ?branch= — joriy narxlar shu nuqtaga xos narxlarni hisobga olib qaytariladi."""

    queryset = Product.objects.none()
    serializer_class = ProductSerializer
    capability_map = {
        **REF_MAP,
        "prices": VIEW,
        "set_price": "catalog.prices.manage",
    }
    filterset_class = ProductFilter
    ordering_fields = ["name", "sku", "created_at"]
    ordering = ["name"]

    def get_queryset(self):
        return selectors.products_queryset()

    def get_serializer_class(self):
        if self.action in ("create", "update", "partial_update"):
            return ProductWriteSerializer
        return ProductSerializer

    def _branch_id(self) -> int | None:
        raw = self.request.query_params.get("branch")
        if not raw:
            return None
        branch_id = int(raw)
        ensure_branch_access(self.request.user, branch_id)
        return branch_id

    def _serialize(self, products, many: bool):
        ids = [p.id for p in products] if many else [products.id]
        context = {
            **self.get_serializer_context(),
            "prices_map": selectors.current_prices(ids, self._branch_id()),
        }
        return ProductSerializer(products, many=many, context=context)

    @extend_schema(parameters=[OpenApiParameter("branch", int, required=False)])
    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        return self.get_paginated_response(self._serialize(page, many=True).data)

    @extend_schema(parameters=[OpenApiParameter("branch", int, required=False)])
    def retrieve(self, request, *args, **kwargs):
        return Response(self._serialize(self.get_object(), many=False).data)

    @extend_schema(request=ProductWriteSerializer, responses={201: ProductSerializer})
    def create(self, request, *args, **kwargs):
        serializer = ProductWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        product = services.create_product(actor=request.user, **serializer.validated_data)
        product = selectors.get_product(product.pk)
        return Response(self._serialize(product, many=False).data, status=status.HTTP_201_CREATED)

    @extend_schema(request=ProductWriteSerializer, responses={200: ProductSerializer})
    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        product = self.get_object()
        serializer = ProductWriteSerializer(product, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        product = services.update_product(
            actor=request.user, product=product, **serializer.validated_data
        )
        product = selectors.get_product(product.pk)
        return Response(self._serialize(product, many=False).data)

    @extend_schema(responses=ProductPriceSerializer(many=True))
    @action(detail=True, methods=["get"], pagination_class=None)
    def prices(self, request, pk=None):
        """Narx tarixi (barcha nuqtalar, barcha turlar)."""
        return Response(
            ProductPriceSerializer(selectors.price_history(self.get_object()), many=True).data
        )

    @extend_schema(request=SetPriceSerializer, responses={201: ProductPriceSerializer})
    @action(detail=True, methods=["post"], url_path="set-price")
    def set_price(self, request, pk=None):
        product = self.get_object()
        serializer = SetPriceSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        branch = data.get("branch")
        if branch is not None:
            ensure_branch_access(request.user, branch.pk)
        row = services.set_price(
            actor=request.user,
            product=product,
            price_type=data["price_type"],
            currency=data["currency"],
            amount=data["amount"],
            branch=branch,
            valid_from=data.get("valid_from"),
        )
        row = selectors.price_history(product).get(pk=row.pk)
        return Response(ProductPriceSerializer(row).data, status=status.HTTP_201_CREATED)
