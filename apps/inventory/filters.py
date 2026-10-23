import django_filters
from django.db.models import Q

from apps.catalog import selectors as catalog_selectors
from core.api.filters import DateRangeFilterSet

from .models import (
    Batch,
    StockCount,
    StockCountItem,
    StockLevel,
    StockMovement,
    Transfer,
    WriteOff,
)
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


class TransferFilter(DateRangeFilterSet):
    """direction + branch: in — shu nuqtaga keladigan, out — shu nuqtadan ketadigan.

    branch berilmasa — foydalanuvchining o'z nuqtalariga nisbatan.
    """

    date_field = "created_at"

    status = django_filters.MultipleChoiceFilter(choices=Transfer.Status.choices)
    branch = django_filters.NumberFilter(method="filter_branch")
    direction = django_filters.ChoiceFilter(
        choices=[("in", "in"), ("out", "out")], method="filter_direction"
    )
    from_branch = django_filters.NumberFilter(field_name="from_branch_id")
    to_branch = django_filters.NumberFilter(field_name="to_branch_id")
    has_discrepancy = django_filters.BooleanFilter()
    search = django_filters.CharFilter(field_name="number", lookup_expr="icontains")

    class Meta:
        model = Transfer
        fields = ["status", "from_branch", "to_branch", "has_discrepancy"]

    def filter_branch(self, queryset, name, value):
        direction = self.data.get("direction")
        if direction == "in":
            return queryset.filter(to_branch_id=value)
        if direction == "out":
            return queryset.filter(from_branch_id=value)
        return queryset.filter(Q(from_branch_id=value) | Q(to_branch_id=value))

    def filter_direction(self, queryset, name, value):
        if self.data.get("branch"):
            return queryset  # filter_branch hisobga oladi
        ids = self.request.user.accessible_branch_ids() if self.request else None
        if ids is None:
            return queryset
        field = "to_branch_id__in" if value == "in" else "from_branch_id__in"
        return queryset.filter(**{field: ids})


class StockCountFilter(DateRangeFilterSet):
    date_field = "created_at"

    branch = django_filters.NumberFilter(field_name="branch_id")
    status = django_filters.MultipleChoiceFilter(choices=StockCount.Status.choices)
    search = django_filters.CharFilter(field_name="number", lookup_expr="icontains")

    class Meta:
        model = StockCount
        fields = ["branch", "status"]


class StockCountItemFilter(django_filters.FilterSet):
    search = django_filters.CharFilter(method="filter_search")
    state = django_filters.ChoiceFilter(
        choices=[("counted", "counted"), ("uncounted", "uncounted"), ("diff", "diff")],
        method="filter_state",
    )

    class Meta:
        model = StockCountItem
        fields = []

    def filter_search(self, queryset, name, value):
        ids = catalog_selectors.search_products(catalog_selectors.products_queryset(), value)
        return queryset.filter(product_id__in=ids.values("id"))

    def filter_state(self, queryset, name, value):
        if value == "counted":
            return queryset.filter(counted_quantity__isnull=False)
        if value == "uncounted":
            return queryset.filter(counted_quantity__isnull=True)
        # farqli: yakunlangan — difference, qoralama — sanalgan ≠ hozirgi qoldiq
        # (diff_value — selectors.count_items annotatsiyasi)
        return queryset.filter(counted_quantity__isnull=False).exclude(diff_value=0)


class WriteOffFilter(DateRangeFilterSet):
    date_field = "completed_at"

    branch = django_filters.NumberFilter(field_name="branch_id")
    reason = django_filters.NumberFilter(field_name="reason_id")
    status = django_filters.MultipleChoiceFilter(choices=WriteOff.Status.choices)
    search = django_filters.CharFilter(field_name="number", lookup_expr="icontains")

    class Meta:
        model = WriteOff
        fields = ["branch", "reason", "status"]
