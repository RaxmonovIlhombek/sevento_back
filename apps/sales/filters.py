import django_filters
from django.db.models import Q

from core.api.filters import DateRangeFilterSet

from .models import Sale


class SaleFilter(DateRangeFilterSet):
    date_field = "completed_at"

    branch = django_filters.NumberFilter(field_name="branch_id")
    seller = django_filters.NumberFilter(field_name="seller_id")
    status = django_filters.ChoiceFilter(choices=Sale.Status.choices)
    currency = django_filters.CharFilter(field_name="currency__code", lookup_expr="iexact")
    search = django_filters.CharFilter(method="filter_search")

    class Meta:
        model = Sale
        fields = ["branch", "seller", "status", "currency"]

    def filter_search(self, queryset, name, value):
        value = value.strip()
        return queryset.filter(
            Q(number__icontains=value) | Q(items__product__name__icontains=value)
        ).distinct()
