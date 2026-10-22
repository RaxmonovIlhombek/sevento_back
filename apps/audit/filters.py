import django_filters

from core.api.filters import DateRangeFilterSet

from .models import AuditLog


class AuditLogFilter(DateRangeFilterSet):
    event_name = django_filters.CharFilter(lookup_expr="exact")
    event_prefix = django_filters.CharFilter(field_name="event_name", lookup_expr="istartswith")

    class Meta:
        model = AuditLog
        fields = ["event_name", "actor", "branch", "aggregate_type", "aggregate_id"]
