from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiParameter, extend_schema, inline_serializer
from rest_framework import mixins, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.branches import selectors as branch_selectors
from core.access import can_access_branch, ensure_branch_access
from core.api.idempotency import idempotent_call
from core.api.mixins import CapabilityViewSetMixin
from core.api.schema import ERROR_RESPONSE

from . import selectors, services
from .filters import (
    BatchFilter,
    MovementFilter,
    StockCountFilter,
    StockCountItemFilter,
    StockFilter,
    TransferFilter,
    WriteOffFilter,
)
from .models import (
    Batch,
    StockCount,
    StockCountItem,
    StockLevel,
    StockMovement,
    Transfer,
    WriteOff,
    WriteOffReason,
)
from .serializers import (
    BatchSerializer,
    BranchBriefSerializer,
    CountedWriteSerializer,
    InventoryCancelSerializer,
    MinQuantitySerializer,
    StockCountCreateSerializer,
    StockCountItemSerializer,
    StockCountListSerializer,
    StockLevelSerializer,
    StockMovementSerializer,
    TransferDetailSerializer,
    TransferListSerializer,
    TransferReceiveSerializer,
    TransferWriteSerializer,
    WriteOffDetailSerializer,
    WriteOffListSerializer,
    WriteOffReasonSerializer,
    WriteOffWriteSerializer,
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


# --- 7-bosqich: ko'chirish ---

T_CREATE, T_RECEIVE, T_CANCEL = (
    "inventory.transfers.create",
    "inventory.transfers.receive",
    "inventory.transfers.cancel",
)
T_VIEW = (T_CREATE, T_RECEIVE, T_CANCEL, "inventory.view_cost")


def transfer_permissions(user, transfer: Transfer) -> dict:
    """Frontend tugmalari uchun: holat + huquq + nuqta (service baribir qayta tekshiradi)."""
    own_from = can_access_branch(user, transfer.from_branch_id)
    own_to = can_access_branch(user, transfer.to_branch_id)
    draft = transfer.status == Transfer.Status.DRAFT
    sent = transfer.status == Transfer.Status.SENT
    return {
        "edit": draft and own_from and user.has_capability(T_CREATE),
        "send": draft and own_from and user.has_capability(T_CREATE),
        "receive": sent and own_to and user.has_capability(T_RECEIVE),
        "cancel": (draft or sent) and own_from and user.has_capability(T_CANCEL),
    }


@extend_schema(tags=["inventory"])
class TransferViewSet(
    CapabilityViewSetMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    """Nuqtalar orasida ko'chirish: qoralama → send → receive (farq bilan ham) | cancel.

    Qabul qiluvchi nuqta qoralamani ko'rmaydi. Holat o'zgarishi ikkala nuqtaga WebSocket orqali.
    """

    queryset = Transfer.objects.none()
    serializer_class = TransferListSerializer
    capability_map = {
        "list": T_VIEW,
        "retrieve": T_VIEW,
        "incoming": T_VIEW,
        "destinations": T_CREATE,
        "create": T_CREATE,
        "update": T_CREATE,
        "send": T_CREATE,
        "receive": T_RECEIVE,
        "cancel": T_CANCEL,
    }
    filterset_class = TransferFilter
    ordering_fields = ["created_at", "sent_at", "received_at", "number"]
    ordering = ["-created_at", "-id"]
    http_method_names = ["get", "post", "put", "patch", "head", "options"]

    def get_queryset(self):
        if self.action == "list":
            return selectors.transfers_queryset(self.request.user)
        return selectors.transfer_detail_queryset(self.request.user)

    def _detail(self, transfer_id: int) -> dict:
        transfer = selectors.transfer_detail_queryset(self.request.user).get(pk=transfer_id)
        transfer.allowed = transfer_permissions(self.request.user, transfer)
        return TransferDetailSerializer(transfer, context=self.get_serializer_context()).data

    @extend_schema(responses=TransferDetailSerializer)
    def retrieve(self, request, *args, **kwargs):
        return Response(self._detail(self.get_object().pk))

    @extend_schema(request=TransferWriteSerializer, responses={201: TransferDetailSerializer})
    def create(self, request, *args, **kwargs):
        serializer = TransferWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        transfer = services.create_transfer(actor=request.user, **serializer.validated_data)
        return Response(self._detail(transfer.pk), status=status.HTTP_201_CREATED)

    @extend_schema(request=TransferWriteSerializer, responses=TransferDetailSerializer)
    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        transfer = self.get_object()
        serializer = TransferWriteSerializer(data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        services.update_transfer(
            actor=request.user, transfer=transfer, items=data.pop("items", None), **data
        )
        return Response(self._detail(transfer.pk))

    @extend_schema(request=None, responses={200: TransferDetailSerializer, 409: ERROR_RESPONSE})
    @action(detail=True, methods=["post"])
    def send(self, request, pk=None):
        """Jo'natish: manbadan FIFO chiqim. Qoldiq yetmasa 409 insufficient_stock (qator bilan)."""
        transfer = self.get_object()

        def handler():
            services.send_transfer(actor=request.user, transfer=transfer)
            return Response(self._detail(transfer.pk))

        return idempotent_call(request, handler)

    @extend_schema(
        request=TransferReceiveSerializer,
        responses={200: TransferDetailSerializer, 409: ERROR_RESPONSE},
    )
    @action(detail=True, methods=["post"])
    def receive(self, request, pk=None):
        """Qabul: items berilmasa hammasi to'liq; kam kelgan qism avtomatik hisobdan chiqariladi."""
        transfer = self.get_object()
        serializer = TransferReceiveSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        def handler():
            services.receive_transfer(
                actor=request.user,
                transfer=transfer,
                received={row["id"]: row["quantity_received"] for row in data["items"]},
                note=data["note"],
            )
            return Response(self._detail(transfer.pk))

        return idempotent_call(request, handler)

    @extend_schema(
        request=InventoryCancelSerializer,
        responses={200: TransferDetailSerializer, 409: ERROR_RESPONSE},
    )
    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        transfer = self.get_object()
        serializer = InventoryCancelSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.cancel_transfer(
            actor=request.user, transfer=transfer, reason=serializer.validated_data["reason"]
        )
        return Response(self._detail(transfer.pk))

    @extend_schema(
        request=None,
        responses=inline_serializer("IncomingTransfers", {"count": serializers.IntegerField()}),
    )
    @action(detail=False, methods=["get"])
    def incoming(self, request):
        """Foydalanuvchi nuqtalariga jo'natilgan, hali qabul qilinmaganlar soni (menyu nishoni)."""
        return Response({"count": selectors.incoming_transfers_count(request.user)})

    @extend_schema(request=None, responses=BranchBriefSerializer(many=True))
    @action(detail=False, methods=["get"], pagination_class=None)
    def destinations(self, request):
        """Qabul qiluvchi nuqta tanlovi: barcha faol nuqtalar (begona nuqtalar ham)."""
        rows = branch_selectors.active_branches().order_by("name")
        return Response(BranchBriefSerializer(rows, many=True).data)


# --- inventarizatsiya ---

C_MANAGE = "inventory.counts.manage"
C_VIEW = (C_MANAGE, "inventory.view_cost")


@extend_schema(tags=["inventory"])
class StockCountViewSet(
    CapabilityViewSetMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    """Inventarizatsiya: yaratish → counted (sanash; qatorlar — /counts/{id}/items/) → complete."""

    queryset = StockCount.objects.none()
    serializer_class = StockCountListSerializer
    capability_map = {
        "list": C_VIEW,
        "retrieve": C_VIEW,
        "create": C_MANAGE,
        "counted": C_MANAGE,
        "complete": C_MANAGE,
        "cancel": C_MANAGE,
    }
    filterset_class = StockCountFilter
    ordering_fields = ["created_at", "completed_at", "number"]
    ordering = ["-created_at", "-id"]

    def get_queryset(self):
        return selectors.counts_queryset(self.request.user)

    def _detail(self, count_id: int) -> dict:
        count = selectors.counts_queryset(self.request.user).get(pk=count_id)
        return StockCountListSerializer(count, context=self.get_serializer_context()).data

    @extend_schema(request=StockCountCreateSerializer, responses={201: StockCountListSerializer})
    def create(self, request, *args, **kwargs):
        serializer = StockCountCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        count = services.create_count(actor=request.user, **serializer.validated_data)
        return Response(self._detail(count.pk), status=status.HTTP_201_CREATED)

    @extend_schema(request=CountedWriteSerializer, responses=StockCountListSerializer)
    @action(detail=True, methods=["post"])
    def counted(self, request, pk=None):
        """Sanalgan miqdorlarni saqlash (bir nechta qator). null — sanalmagan holatga qaytarish."""
        count = self.get_object()
        serializer = CountedWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.set_counted(
            actor=request.user, count=count, items=serializer.validated_data["items"]
        )
        return Response(self._detail(count.pk))

    @extend_schema(request=None, responses={200: StockCountListSerializer, 409: ERROR_RESPONSE})
    @action(detail=True, methods=["post"])
    def complete(self, request, pk=None):
        count = self.get_object()

        def handler():
            services.complete_count(actor=request.user, count=count)
            return Response(self._detail(count.pk))

        return idempotent_call(request, handler)

    @extend_schema(request=None, responses={200: StockCountListSerializer, 409: ERROR_RESPONSE})
    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        count = self.get_object()
        services.cancel_count(actor=request.user, count=count)
        return Response(self._detail(count.pk))


@extend_schema(
    tags=["inventory"],
    parameters=[OpenApiParameter("count_pk", int, OpenApiParameter.PATH)],
)
class StockCountItemViewSet(CapabilityViewSetMixin, mixins.ListModelMixin, viewsets.GenericViewSet):
    """Inventarizatsiya qatorlari (sahifalangan): search, state=counted|uncounted|diff.

    current_quantity — hozirgi qoldiq (qoralamada yakunlash shu bilan solishtiradi).
    """

    queryset = StockCountItem.objects.none()
    serializer_class = StockCountItemSerializer
    capability_map = {"list": C_VIEW}
    filterset_class = StockCountItemFilter
    ordering_fields = ["product__name", "product__sku"]
    ordering = ["product__name", "id"]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return StockCountItem.objects.none()
        count = get_object_or_404(
            selectors.counts_queryset(self.request.user), pk=self.kwargs["count_pk"]
        )
        return selectors.count_items(count)


# --- hisobdan chiqarish ---

W_MANAGE = "inventory.writeoffs.manage"
W_VIEW = (W_MANAGE, "inventory.view_cost")


@extend_schema(tags=["inventory"])
class WriteOffReasonViewSet(
    CapabilityViewSetMixin,
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
    mixins.ListModelMixin,
    viewsets.GenericViewSet,
):
    """Hisobdan chiqarish sabablari (ma'lumotnoma). Tizim sababi qo'lda tanlanmaydi."""

    queryset = WriteOffReason.objects.none()
    serializer_class = WriteOffReasonSerializer
    capability_map = {"list": W_VIEW, "create": "settings.manage", "update": "settings.manage"}
    pagination_class = None
    filterset_fields = ["is_active", "is_system"]
    ordering = ["name"]

    def get_queryset(self):
        return selectors.write_off_reasons()

    def perform_create(self, serializer):
        serializer.instance = services.save_reason(
            actor=self.request.user, **serializer.validated_data
        )

    def perform_update(self, serializer):
        serializer.instance = services.save_reason(
            actor=self.request.user, reason=serializer.instance, **serializer.validated_data
        )


@extend_schema(tags=["inventory"])
class WriteOffViewSet(
    CapabilityViewSetMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    """Hisobdan chiqarish: POST darhol yakunlaydi (FIFO chiqim); cancel — asl partiyalarga."""

    queryset = WriteOff.objects.none()
    serializer_class = WriteOffListSerializer
    capability_map = {
        "list": W_VIEW,
        "retrieve": W_VIEW,
        "create": W_MANAGE,
        "cancel": W_MANAGE,
    }
    filterset_class = WriteOffFilter
    ordering_fields = ["completed_at", "number", "total_cost_base"]
    ordering = ["-completed_at", "-id"]

    def get_queryset(self):
        if self.action == "list":
            return selectors.write_offs_queryset(self.request.user)
        return selectors.write_off_detail_queryset(self.request.user)

    def _detail(self, write_off_id: int) -> dict:
        write_off = selectors.write_off_detail_queryset(self.request.user).get(pk=write_off_id)
        user = self.request.user
        write_off.can_cancel = (
            write_off.status == WriteOff.Status.COMPLETED
            and write_off.transfer_id is None
            and user.has_capability(W_MANAGE)
            and can_access_branch(user, write_off.branch_id)
        )
        return WriteOffDetailSerializer(write_off, context=self.get_serializer_context()).data

    @extend_schema(responses=WriteOffDetailSerializer)
    def retrieve(self, request, *args, **kwargs):
        return Response(self._detail(self.get_object().pk))

    @extend_schema(
        request=WriteOffWriteSerializer,
        responses={201: WriteOffDetailSerializer, 409: ERROR_RESPONSE},
    )
    def create(self, request, *args, **kwargs):
        serializer = WriteOffWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        def handler():
            write_off = services.create_write_off(actor=request.user, **serializer.validated_data)
            return Response(self._detail(write_off.pk), status=status.HTTP_201_CREATED)

        return idempotent_call(request, handler)

    @extend_schema(
        request=InventoryCancelSerializer,
        responses={200: WriteOffDetailSerializer, 409: ERROR_RESPONSE},
    )
    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        write_off = self.get_object()
        serializer = InventoryCancelSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.cancel_write_off(
            actor=request.user, write_off=write_off, reason=serializer.validated_data["reason"]
        )
        return Response(self._detail(write_off.pk))
