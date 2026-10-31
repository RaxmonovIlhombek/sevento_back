import django_filters

from .models import ApprovalInstance, ApprovalRule


class ApprovalRuleFilter(django_filters.FilterSet):
    entity_type = django_filters.CharFilter()
    is_active = django_filters.BooleanFilter()

    class Meta:
        model = ApprovalRule
        fields = ["entity_type", "is_active"]


class ApprovalInstanceFilter(django_filters.FilterSet):
    entity_type = django_filters.CharFilter()
    status = django_filters.ChoiceFilter(choices=ApprovalInstance.Status.choices)
    branch = django_filters.NumberFilter(field_name="branch_id")

    class Meta:
        model = ApprovalInstance
        fields = ["entity_type", "status", "branch"]
