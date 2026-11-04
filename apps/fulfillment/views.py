from drf_spectacular.utils import extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.filters import SearchFilter
from rest_framework.response import Response

from core.api.mixins import CapabilityViewSetMixin

from . import selectors, services
from .filters import FulfillmentFilter
from .models import Fulfillment
from .serializers import (
    FulfillmentCreateSerializer,
    FulfillmentDetailSerializer,
    FulfillmentSerializer,
    NoteSerializer,
    ReasonSerializer,
    SummarySerializer,
)

VIEW = (
    "fulfillment.view",
    "fulfillment.pack",
    "fulfillment.verify",
    "deliveries.view",
    "sales.create",
)


class FulfillmentViewSet(
    CapabilityViewSetMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    viewsets.GenericViewSet,
):
    """Yetkazish jarayoni: omborchi taxlaydi → operator tekshiradi → kuryer yetkazadi."""

    queryset = Fulfillment.objects.none()
    serializer_class = FulfillmentSerializer
    capability_map = {
        "list": VIEW,
        "retrieve": VIEW,
        "summary": VIEW,
        "create": ("sales.create", "fulfillment.manage"),
        "pack": "fulfillment.pack",
        "verify": "fulfillment.verify",
        "reject": "fulfillment.verify",
        "accept": "deliveries.manage",
        "deliver": "deliveries.manage",
        "cancel": "fulfillment.manage",
    }
    filterset_class = FulfillmentFilter
    filter_backends = [*viewsets.GenericViewSet.filter_backends, SearchFilter]
    search_fields = ["sale__number", "address", "contact_phone", "sale__customer__name"]
    ordering = ["-created_at", "-id"]

    def get_queryset(self):
        user = self.request.user
        if self.action == "retrieve":
            return selectors.fulfillment_detail_queryset(user)
        return selectors.fulfillments_queryset(user)

    def get_serializer_class(self):
        if self.action == "retrieve":
            return FulfillmentDetailSerializer
        if self.action == "create":
            return FulfillmentCreateSerializer
        return FulfillmentSerializer

    def _respond(self, fulfillment) -> Response:
        fresh = selectors.fulfillment_detail_queryset(self.request.user).get(pk=fulfillment.pk)
        return Response(FulfillmentDetailSerializer(fresh).data)

    @extend_schema(
        request=FulfillmentCreateSerializer, responses={201: FulfillmentDetailSerializer}
    )
    def create(self, request, *args, **kwargs):
        serializer = FulfillmentCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        f = services.create_for_sale(
            actor=request.user,
            sale=data["sale"],
            address=data["address"],
            contact_phone=data["contact_phone"],
            note=data["note"],
        )
        response = self._respond(f)
        response.status_code = status.HTTP_201_CREATED
        return response

    @extend_schema(responses=SummarySerializer)
    @action(detail=False, methods=["get"])
    def summary(self, request):
        return Response(selectors.status_counts(self.get_queryset()))

    @extend_schema(request=NoteSerializer, responses=FulfillmentDetailSerializer)
    @action(detail=True, methods=["post"])
    def pack(self, request, pk=None):
        note = self._body(NoteSerializer, request).get("note", "")
        return self._respond(
            services.pack(actor=request.user, fulfillment_id=self.get_object().pk, note=note)
        )

    @extend_schema(request=NoteSerializer, responses=FulfillmentDetailSerializer)
    @action(detail=True, methods=["post"])
    def verify(self, request, pk=None):
        note = self._body(NoteSerializer, request).get("note", "")
        return self._respond(
            services.verify(actor=request.user, fulfillment_id=self.get_object().pk, note=note)
        )

    @extend_schema(request=ReasonSerializer, responses=FulfillmentDetailSerializer)
    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        reason = self._body(ReasonSerializer, request)["reason"]
        return self._respond(
            services.reject(actor=request.user, fulfillment_id=self.get_object().pk, reason=reason)
        )

    @extend_schema(request=None, responses=FulfillmentDetailSerializer)
    @action(detail=True, methods=["post"])
    def accept(self, request, pk=None):
        return self._respond(
            services.accept(actor=request.user, fulfillment_id=self.get_object().pk)
        )

    @extend_schema(request=NoteSerializer, responses=FulfillmentDetailSerializer)
    @action(detail=True, methods=["post"])
    def deliver(self, request, pk=None):
        note = self._body(NoteSerializer, request).get("note", "")
        return self._respond(
            services.deliver(actor=request.user, fulfillment_id=self.get_object().pk, note=note)
        )

    @extend_schema(request=ReasonSerializer, responses=FulfillmentDetailSerializer)
    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        reason = self._body(ReasonSerializer, request)["reason"]
        return self._respond(
            services.cancel(actor=request.user, fulfillment_id=self.get_object().pk, reason=reason)
        )

    @staticmethod
    def _body(serializer_class, request) -> dict:
        serializer = serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        return serializer.validated_data
