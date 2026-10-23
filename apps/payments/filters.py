import django_filters

from core.api.filters import DateRangeFilterSet

from .models import Cashbox, CashTransaction
from .types import Direction


class CashboxFilter(django_filters.FilterSet):
    branch = django_filters.NumberFilter(field_name="branch_id")
    currency = django_filters.CharFilter(field_name="currency__code", lookup_expr="iexact")

    class Meta:
        model = Cashbox
        fields = ["branch", "currency", "is_active"]


class CashTransactionFilter(DateRangeFilterSet):
    cashbox = django_filters.NumberFilter(field_name="cashbox_id")
    branch = django_filters.NumberFilter(field_name="cashbox__branch_id")
    direction = django_filters.ChoiceFilter(choices=Direction.choices)
    category = django_filters.CharFilter(field_name="category__code")

    class Meta:
        model = CashTransaction
        fields = ["cashbox", "branch", "direction", "category"]
