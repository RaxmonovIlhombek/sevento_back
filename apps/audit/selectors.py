from django.db.models import QuerySet

from .models import AuditLog


def audit_queryset() -> QuerySet[AuditLog]:
    return AuditLog.objects.select_related("actor", "branch")
