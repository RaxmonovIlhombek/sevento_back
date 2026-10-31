import django_filters

from .models import Activity, Deal, Lead


class LeadFilter(django_filters.FilterSet):
    status = django_filters.ChoiceFilter(choices=Lead.Status.choices)
    branch = django_filters.NumberFilter(field_name="branch_id")
    owner = django_filters.NumberFilter(field_name="owner_id")

    class Meta:
        model = Lead
        fields = ["status", "branch", "owner"]


class DealFilter(django_filters.FilterSet):
    stage = django_filters.ChoiceFilter(choices=Deal.Stage.choices)
    branch = django_filters.NumberFilter(field_name="branch_id")
    owner = django_filters.NumberFilter(field_name="owner_id")
    lead = django_filters.ModelChoiceFilter(queryset=Lead.objects.all())

    class Meta:
        model = Deal
        fields = ["stage", "branch", "owner", "lead"]


class ActivityFilter(django_filters.FilterSet):
    activity_type = django_filters.ChoiceFilter(choices=Activity.Type.choices)
    completed = django_filters.BooleanFilter()
    lead = django_filters.ModelChoiceFilter(queryset=Lead.objects.all())
    deal = django_filters.ModelChoiceFilter(queryset=Deal.objects.all())

    class Meta:
        model = Activity
        fields = ["activity_type", "completed", "lead", "deal"]
