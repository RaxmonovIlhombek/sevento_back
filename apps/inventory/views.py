from drf_spectacular.utils import extend_schema
from rest_framework import mixins, viewsets
from rest_framework.response import Response

from core.access import ensure_branch_access
from core.api.mixins import CapabilityViewSetMixin

from . import selectors, services
from .filters import BatchFilter, MovementFilter, StockFilter
from .models import Batch, StockLevel, StockMovement
from .serializers import (
    BatchSerializer,
    MinQuantitySerializer,
    StockLevelSerializer,
    StockMovementSerializer,
)


@extend_schema(tags=["inventory"])
class StockViewSet(
    CapabilityViewSetMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    """Qoldiqlar (o'z nuqtalari). PATCH — faqat nuqtaga xos minimal qoldiq (inventory.manage)."""

    queryset = StockLevel.objects.none()
    serializer_class = StockLevelSerializer
    capability_map = {
        "list": "inventory.view",
        "retrieve": "inventory.view",
        "update": "inventory.manage",
    }
    filterset_class = StockFilter
    ordering_fields = ["product__name", "quantity", "updated_at", "value_base"]
    ordering = ["product__name", "branch__name"]
    http_method_names = ["get", "patch", "head", "options"]

    def get_queryset(self):
        return selectors.stock_queryset(self.request.user)

    @extend_schema(request=MinQuantitySerializer, responses=StockLevelSerializer)
    def partial_update(self, request, *args, **kwargs):
        level = self.get_object()
        ensure_branch_access(request.user, level.branch_id)
        serializer = MinQuantitySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.set_min_quantity(
            actor=request.user, level=level, min_quantity=serializer.validated_data["min_quantity"]
        )
        level = self.get_queryset().get(pk=level.pk)
        return Response(self.get_serializer(level).data)


@extend_schema(tags=["inventory"])
class BatchViewSet(CapabilityViewSetMixin, viewsets.ReadOnlyModelViewSet):
    """Partiyalar va ularning tannarxi — inventory.view_cost."""

    queryset = Batch.objects.none()
    serializer_class = BatchSerializer
    capability_map = {"list": "inventory.view_cost", "retrieve": "inventory.view_cost"}
    filterset_class = BatchFilter
    ordering_fields = ["received_at", "quantity_remaining"]
    ordering = ["received_at", "id"]

    def get_queryset(self):
        return selectors.batches_queryset(self.request.user)


@extend_schema(tags=["inventory"])
class MovementViewSet(CapabilityViewSetMixin, viewsets.ReadOnlyModelViewSet):
    """Ombor harakatlari jurnali. Tannarx ustunlari — faqat inventory.view_cost bilan."""

    queryset = StockMovement.objects.none()
    serializer_class = StockMovementSerializer
    capability_map = {"list": "inventory.view", "retrieve": "inventory.view"}
    filterset_class = MovementFilter
    search_fields = ["product__name", "product__sku", "document_number"]
    ordering_fields = ["created_at", "quantity"]
    ordering = ["-created_at", "-id"]

    def get_queryset(self):
        return selectors.movements_queryset(self.request.user)
