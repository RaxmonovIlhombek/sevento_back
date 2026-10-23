import django_filters
from django.db.models import Q

from core.api.filters import DateRangeFilterSet

from .models import Purchase


class PurchaseFilter(DateRangeFilterSet):
    branch = django_filters.NumberFilter(field_name="branch_id")
    supplier = django_filters.NumberFilter(field_name="supplier_id")
    status = django_filters.MultipleChoiceFilter(choices=Purchase.Status.choices)
    search = django_filters.CharFilter(method="filter_search")

    class Meta:
        model = Purchase
        fields = ["branch", "supplier", "status", "currency"]

    def filter_search(self, queryset, name, value):
        value = value.strip()
        if not value:
            return queryset
        return queryset.filter(
            Q(number__icontains=value)
            | Q(invoice_number__icontains=value)
            | Q(supplier__name__icontains=value)
        )
