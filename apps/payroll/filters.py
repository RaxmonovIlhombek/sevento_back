import django_filters

from .models import PayrollRun


class PayrollRunFilter(django_filters.FilterSet):
    status = django_filters.ChoiceFilter(choices=PayrollRun.Status.choices)
    branch = django_filters.NumberFilter(field_name="branch_id")

    class Meta:
        model = PayrollRun
        fields = ["status", "branch"]
