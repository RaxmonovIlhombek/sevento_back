import django_filters

from apps.catalog import selectors as catalog_selectors
from core.api.filters import DateRangeFilterSet

from .models import Batch, StockLevel, StockMovement
from .types import MovementType


class StockFilter(django_filters.FilterSet):
    branch = django_filters.NumberFilter(field_name="branch_id")
    product = django_filters.NumberFilter(field_name="product_id")
    category = django_filters.NumberFilter(method="filter_category")
    search = django_filters.CharFilter(method="filter_search")
    below_minimum = django_filters.BooleanFilter(field_name="is_below_min")
    in_stock = django_filters.BooleanFilter(method="filter_in_stock")

    class Meta:
        model = StockLevel
        fields = ["branch", "product"]

    def filter_category(self, queryset, name, value):
        return queryset.filter(
            product__category_id__in=catalog_selectors.descendant_ids(int(value))
        )

    def filter_search(self, queryset, name, value):
        ids = catalog_selectors.search_products(catalog_selectors.products_queryset(), value)
        return queryset.filter(product_id__in=ids.values("id"))

    def filter_in_stock(self, queryset, name, value):
        return queryset.filter(quantity__gt=0) if value else queryset.filter(quantity=0)


class BatchFilter(django_filters.FilterSet):
    branch = django_filters.NumberFilter(field_name="branch_id")
    product = django_filters.NumberFilter(field_name="product_id")
    open = django_filters.BooleanFilter(method="filter_open")

    class Meta:
        model = Batch
        fields = ["branch", "product", "source_type"]

    def filter_open(self, queryset, name, value):
        return (
            queryset.filter(quantity_remaining__gt=0)
            if value
            else queryset.filter(quantity_remaining=0)
        )


class MovementFilter(DateRangeFilterSet):
    branch = django_filters.NumberFilter(field_name="branch_id")
    product = django_filters.NumberFilter(field_name="product_id")
    type = django_filters.MultipleChoiceFilter(choices=MovementType.choices)
    direction = django_filters.ChoiceFilter(
        choices=[("in", "in"), ("out", "out")], method="filter_direction"
    )

    class Meta:
        model = StockMovement
        fields = ["branch", "product", "type", "document_type", "document_id"]

    def filter_direction(self, queryset, name, value):
        return queryset.filter(quantity__gt=0) if value == "in" else queryset.filter(quantity__lt=0)
