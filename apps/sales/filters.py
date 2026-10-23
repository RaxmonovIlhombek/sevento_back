import django_filters
from django.db.models import Q

from core.api.filters import DateRangeFilterSet

from .models import Sale, SaleReturn


class SaleFilter(DateRangeFilterSet):
    date_field = "completed_at"

    branch = django_filters.NumberFilter(field_name="branch_id")
    seller = django_filters.NumberFilter(field_name="seller_id")
    status = django_filters.ChoiceFilter(choices=Sale.Status.choices)
    currency = django_filters.CharFilter(field_name="currency__code", lookup_expr="iexact")
    customer = django_filters.NumberFilter(field_name="customer_id")
    on_credit = django_filters.BooleanFilter(method="filter_on_credit")
    search = django_filters.CharFilter(method="filter_search")

    class Meta:
        model = Sale
        fields = ["branch", "seller", "status", "currency"]

    def filter_on_credit(self, queryset, name, value):
        return queryset.filter(debt_amount__gt=0) if value else queryset.filter(debt_amount=0)

    def filter_search(self, queryset, name, value):
        value = value.strip()
        return queryset.filter(
            Q(number__icontains=value) | Q(items__product__name__icontains=value)
        ).distinct()


class SaleReturnFilter(DateRangeFilterSet):
    date_field = "created_at"

    branch = django_filters.NumberFilter(field_name="branch_id")
    sale = django_filters.NumberFilter(field_name="sale_id")
    customer = django_filters.NumberFilter(field_name="customer_id")
    search = django_filters.CharFilter(method="filter_search")

    class Meta:
        model = SaleReturn
        fields = ["branch", "sale", "customer"]

    def filter_search(self, queryset, name, value):
        value = value.strip()
        return queryset.filter(Q(number__icontains=value) | Q(sale__number__icontains=value))
