from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.filters import OrderingFilter
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .filters import ApprovalInstanceFilter, ApprovalRuleFilter
from .models import ApprovalInstance, ApprovalRule, ApprovalStep
from .serializers import ApprovalInstanceSerializer, ApprovalRuleSerializer, ApprovalStepSerializer


class ApprovalRuleViewSet(viewsets.ModelViewSet):
    queryset = ApprovalRule.objects.select_related("approver", "branch").all()
    serializer_class = ApprovalRuleSerializer
    permission_classes = [IsAuthenticated]
    filterset_class = ApprovalRuleFilter
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    ordering = ["entity_type", "sequence"]


class ApprovalInstanceViewSet(viewsets.ModelViewSet):
    queryset = ApprovalInstance.objects.select_related("requested_by", "branch").prefetch_related("steps__approver").all()
    serializer_class = ApprovalInstanceSerializer
    permission_classes = [IsAuthenticated]
    filterset_class = ApprovalInstanceFilter
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    ordering = ["-created_at"]

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        instance = self.get_object()
        if instance.status != ApprovalInstance.Status.PENDING:
            return Response({"detail": "Kutilmayotgan so'rov"}, status=400)
        step = instance.steps.filter(approver=request.user, decision=ApprovalStep.Decision.PENDING).first()
        if not step:
            return Response({"detail": "Siz tasdiqlay olmaysiz"}, status=403)
        step.decision = ApprovalStep.Decision.APPROVED
        step.decided_at = __import__("django.utils.timezone", fromlist=["now"]).now()
        step.comment = request.data.get("comment", "")
        step.save()
        if not instance.steps.filter(decision=ApprovalStep.Decision.PENDING).exists():
            instance.status = ApprovalInstance.Status.APPROVED
            instance.decided_at = step.decided_at
            instance.save(update_fields=["status", "decided_at", "updated_at"])
        return Response(self.get_serializer(instance).data)

    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        instance = self.get_object()
        if instance.status != ApprovalInstance.Status.PENDING:
            return Response({"detail": "Kutilmayotgan so'rov"}, status=400)
        step = instance.steps.filter(approver=request.user, decision=ApprovalStep.Decision.PENDING).first()
        if not step:
            return Response({"detail": "Siz rad eta olmaysiz"}, status=403)
        step.decision = ApprovalStep.Decision.REJECTED
        step.decided_at = __import__("django.utils.timezone", fromlist=["now"]).now()
        step.comment = request.data.get("comment", "")
        step.save()
        instance.status = ApprovalInstance.Status.REJECTED
        instance.decided_at = step.decided_at
        instance.save(update_fields=["status", "decided_at", "updated_at"])
        return Response(self.get_serializer(instance).data)
