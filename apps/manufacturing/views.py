from django.db import transaction
from django.utils import timezone
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from django.db import transaction

from core.models import DocumentSequence
from django_filters.rest_framework import DjangoFilterBackend

from .filters import BillOfMaterialsFilter, ProductionOrderFilter
from .models import BillOfMaterials, ProductionOrder
from .serializers import BillOfMaterialsSerializer, ProductionOrderSerializer


class BillOfMaterialsViewSet(viewsets.ModelViewSet):
    queryset = BillOfMaterials.objects.select_related("product").prefetch_related("items__component")
    serializer_class = BillOfMaterialsSerializer
    permission_classes = [IsAuthenticated]
    filterset_class = BillOfMaterialsFilter
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    search_fields = ["name", "product__name"]
    ordering = ["-created_at"]


class ProductionOrderViewSet(viewsets.ModelViewSet):
    queryset = ProductionOrder.objects.select_related("product", "bom", "branch", "created_by").all()
    serializer_class = ProductionOrderSerializer
    permission_classes = [IsAuthenticated]
    filterset_class = ProductionOrderFilter
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    search_fields = ["number", "product__name"]
    ordering = ["-created_at"]

    @transaction.atomic
    def perform_create(self, serializer):
        branch = serializer.validated_data["branch"]
        seq, _ = DocumentSequence.objects.select_for_update().get_or_create(
            doc_type="PO", branch_id=branch.pk, year=timezone.now().year
        )
        seq.last_number += 1
        seq.save(update_fields=["last_number"])
        number = f"PO-{timezone.now().year}-{seq.last_number:05d}"
        serializer.save(number=number, created_by=self.request.user)

    @action(detail=True, methods=["post"])
    def release(self, request, pk=None):
        order = self.get_object()
        if order.status != ProductionOrder.Status.DRAFT:
            return Response({"detail": "Faqat qoralamani ishga tushirish mumkin"}, status=400)
        order.status = ProductionOrder.Status.RELEASED
        order.actual_start = timezone.now()
        order.save(update_fields=["status", "actual_start", "updated_at"])
        return Response(self.get_serializer(order).data)

    @action(detail=True, methods=["post"])
    def complete(self, request, pk=None):
        order = self.get_object()
        if order.status not in (ProductionOrder.Status.RELEASED, ProductionOrder.Status.IN_PROGRESS):
            return Response({"detail": "Yakunlab bo'lmaydi"}, status=400)
        order.status = ProductionOrder.Status.COMPLETED
        order.actual_end = timezone.now()
        order.save(update_fields=["status", "actual_end", "updated_at"])
        return Response(self.get_serializer(order).data)
