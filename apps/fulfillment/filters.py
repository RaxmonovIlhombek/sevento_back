import django_filters

from .models import Fulfillment


class FulfillmentFilter(django_filters.FilterSet):
    status = django_filters.MultipleChoiceFilter(choices=Fulfillment.Status.choices)
    branch = django_filters.NumberFilter(field_name="branch_id")
    courier = django_filters.NumberFilter(field_name="courier_id")
    sale = django_filters.NumberFilter(field_name="sale_id")
    mine = django_filters.BooleanFilter(method="filter_mine")

    class Meta:
        model = Fulfillment
        fields = ["status", "branch", "courier", "sale"]

    def filter_mine(self, queryset, name, value):
        if value:
            return queryset.filter(courier=self.request.user)
        return queryset
