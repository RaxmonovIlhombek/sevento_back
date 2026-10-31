import django_filters

from .models import Account, JournalEntry


class AccountFilter(django_filters.FilterSet):
    account_type = django_filters.ChoiceFilter(choices=Account.Type.choices)
    is_active = django_filters.BooleanFilter()
    is_postable = django_filters.BooleanFilter()
    parent = django_filters.ModelChoiceFilter(queryset=Account.objects.all())

    class Meta:
        model = Account
        fields = ["account_type", "is_active", "is_postable", "parent"]


class JournalEntryFilter(django_filters.FilterSet):
    status = django_filters.ChoiceFilter(choices=JournalEntry.Status.choices)
    date_from = django_filters.DateFilter(field_name="date", lookup_expr="gte")
    date_to = django_filters.DateFilter(field_name="date", lookup_expr="lte")
    branch = django_filters.NumberFilter(field_name="branch_id")
    fiscal_period = django_filters.NumberFilter(field_name="fiscal_period_id")

    class Meta:
        model = JournalEntry
        fields = ["status", "branch", "fiscal_period"]
