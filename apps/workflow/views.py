from django.db.models import Q
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.filters import OrderingFilter
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.access import can_access_branch
from core.api.mixins import CapabilityViewSetMixin

from . import services
from .filters import ApprovalInstanceFilter, ApprovalRuleFilter
from .models import ApprovalInstance, ApprovalRule
from .serializers import (
    ApprovalInstanceSerializer,
    ApprovalRuleSerializer,
    CreateRequestSerializer,
    DecisionSerializer,
    WorkflowSummarySerializer,
)

MANAGE = "workflow.manage"


class ApprovalRuleViewSet(CapabilityViewSetMixin, viewsets.ModelViewSet):
    """Qoidalar: faqat rahbar (workflow.manage) ko'radi va boshqaradi."""

    queryset = ApprovalRule.objects.select_related("approver", "branch").all()
    serializer_class = ApprovalRuleSerializer
    filterset_class = ApprovalRuleFilter
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    ordering = ["entity_type", "sequence"]
    capability_map = {
        "list": MANAGE,
        "retrieve": MANAGE,
        "create": MANAGE,
        "update": MANAGE,
        "partial_update": MANAGE,
        "destroy": MANAGE,
    }


class ApprovalInstanceViewSet(
    mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet
):
    """So'rovlar. Oddiy foydalanuvchi faqat o'zi yuborgan yoki tasdiqlovchi bo'lganini ko'radi."""

    serializer_class = ApprovalInstanceSerializer
    permission_classes = [IsAuthenticated]
    filterset_class = ApprovalInstanceFilter
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    ordering = ["-created_at"]

    queryset = ApprovalInstance.objects.none()

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return ApprovalInstance.objects.none()
        qs = ApprovalInstance.objects.select_related("requested_by", "branch").prefetch_related(
            "steps__approver"
        )
        user = self.request.user
        if getattr(user, "is_authenticated", False) and user.has_capability(MANAGE):
            return qs
        return qs.filter(Q(requested_by=user) | Q(steps__approver=user)).distinct()

    @extend_schema(request=CreateRequestSerializer, responses=ApprovalInstanceSerializer)
    def create(self, request):
        serializer = CreateRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        branch_id = data.get("branch")
        if branch_id is not None and not can_access_branch(request.user, branch_id):
            return Response({"branch": ["Bu nuqtaga kirish huquqingiz yo'q"]}, status=400)
        instance = services.create_request(
            actor=request.user,
            entity_type=data["entity_type"],
            title=data["title"],
            amount=data["amount"],
            branch_id=branch_id,
            notes=data["notes"],
        )
        return Response(self._detail(instance), status=status.HTTP_201_CREATED)

    def _detail(self, instance):
        instance = self.get_queryset().get(pk=instance.pk)
        return self.get_serializer(instance).data

    @extend_schema(request=DecisionSerializer, responses=ApprovalInstanceSerializer)
    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        body = DecisionSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        instance = services.decide(
            actor=request.user,
            instance=self.get_object(),
            approve=True,
            comment=body.validated_data["comment"],
        )
        return Response(self._detail(instance))

    @extend_schema(request=DecisionSerializer, responses=ApprovalInstanceSerializer)
    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        body = DecisionSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        instance = services.decide(
            actor=request.user,
            instance=self.get_object(),
            approve=False,
            comment=body.validated_data["comment"],
        )
        return Response(self._detail(instance))

    @extend_schema(request=None, responses=ApprovalInstanceSerializer)
    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        instance = services.cancel_request(actor=request.user, instance=self.get_object())
        return Response(self._detail(instance))

    @extend_schema(responses=WorkflowSummarySerializer)
    @action(detail=False, methods=["get"], pagination_class=None)
    def summary(self, request):
        """Menyu/tablar uchun sonlar: menga kelgan va o'zim yuborgan kutilayotganlar."""
        user = request.user
        pending = ApprovalInstance.Status.PENDING
        assigned = ApprovalInstanceFilter(
            {"scope": "assigned"}, queryset=self.get_queryset(), request=request
        ).qs.count()
        mine = ApprovalInstance.objects.filter(requested_by=user, status=pending).count()
        return Response({"assigned": assigned, "mine_pending": mine})
