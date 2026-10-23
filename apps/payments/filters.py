import django_filters
from django.db.models import Exists, OuterRef, Q
from django.utils import timezone

from core.api.filters import DateRangeFilterSet

from .models import Cashbox, CashShift, CashTransaction, Customer, Debt, Payment
from .types import Direction, PaymentKind


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
    shift = django_filters.NumberFilter(field_name="shift_id")

    class Meta:
        model = CashTransaction
        fields = ["cashbox", "branch", "direction", "category", "shift"]


class CustomerFilter(django_filters.FilterSet):
    search = django_filters.CharFilter(method="filter_search")
    has_debt = django_filters.BooleanFilter(method="filter_has_debt")
    overdue = django_filters.BooleanFilter(method="filter_overdue")

    class Meta:
        model = Customer
        fields = ["is_active"]

    def filter_search(self, queryset, name, value):
        value = value.strip()
        return queryset.filter(
            Q(name__icontains=value) | Q(phone__icontains=value) | Q(tin__icontains=value)
        )

    def filter_has_debt(self, queryset, name, value):
        open_debt = Exists(Debt.objects.filter(customer=OuterRef("pk"), status=Debt.Status.OPEN))
        return queryset.filter(open_debt) if value else queryset.exclude(open_debt)

    def filter_overdue(self, queryset, name, value):
        overdue = Exists(
            Debt.objects.filter(
                customer=OuterRef("pk"),
                status=Debt.Status.OPEN,
                due_date__lt=timezone.localdate(),
            )
        )
        return queryset.filter(overdue) if value else queryset.exclude(overdue)


class DebtFilter(django_filters.FilterSet):
    customer = django_filters.NumberFilter(field_name="customer_id")
    branch = django_filters.NumberFilter(field_name="branch_id")
    status = django_filters.ChoiceFilter(choices=Debt.Status.choices)
    currency = django_filters.CharFilter(field_name="currency__code", lookup_expr="iexact")
    overdue = django_filters.BooleanFilter(method="filter_overdue")
    due_from = django_filters.DateFilter(field_name="due_date", lookup_expr="gte")
    due_to = django_filters.DateFilter(field_name="due_date", lookup_expr="lte")
    search = django_filters.CharFilter(method="filter_search")

    class Meta:
        model = Debt
        fields = ["customer", "branch", "status", "currency"]

    def filter_overdue(self, queryset, name, value):
        cond = Q(status=Debt.Status.OPEN, due_date__lt=timezone.localdate())
        return queryset.filter(cond) if value else queryset.exclude(cond)

    def filter_search(self, queryset, name, value):
        value = value.strip()
        return queryset.filter(
            Q(customer__name__icontains=value)
            | Q(customer__phone__icontains=value)
            | Q(document_number__icontains=value)
        )


class PaymentFilter(DateRangeFilterSet):
    date_field = "received_at"

    branch = django_filters.NumberFilter(field_name="branch_id")
    customer = django_filters.NumberFilter(field_name="customer_id")
    method = django_filters.CharFilter(field_name="method__code")
    kind = django_filters.ChoiceFilter(choices=PaymentKind.choices)
    direction = django_filters.ChoiceFilter(choices=Direction.choices)
    document_type = django_filters.CharFilter(field_name="document_type")
    search = django_filters.CharFilter(method="filter_search")

    class Meta:
        model = Payment
        fields = ["branch", "customer", "kind", "direction", "document_type"]

    def filter_search(self, queryset, name, value):
        value = value.strip()
        return queryset.filter(
            Q(number__icontains=value)
            | Q(document_number__icontains=value)
            | Q(customer__name__icontains=value)
        )


class CashShiftFilter(DateRangeFilterSet):
    date_field = "opened_at"

    branch = django_filters.NumberFilter(field_name="branch_id")
    status = django_filters.ChoiceFilter(choices=CashShift.Status.choices)

    class Meta:
        model = CashShift
        fields = ["branch", "status"]
