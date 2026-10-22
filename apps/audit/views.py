from drf_spectacular.utils import extend_schema
from rest_framework import viewsets

from core.api.mixins import CapabilityViewSetMixin

from . import selectors
from .filters import AuditLogFilter
from .models import AuditLog
from .serializers import AuditLogSerializer


@extend_schema(tags=["audit"])
class AuditLogViewSet(CapabilityViewSetMixin, viewsets.ReadOnlyModelViewSet):
    queryset = AuditLog.objects.none()
    serializer_class = AuditLogSerializer
    capability_map = {"list": "audit.view", "retrieve": "audit.view"}
    filterset_class = AuditLogFilter
    search_fields = ["actor__username", "actor__full_name", "request_id"]
    ordering_fields = ["created_at", "id"]
    ordering = ["-id"]

    def get_queryset(self):
        return selectors.audit_queryset()
