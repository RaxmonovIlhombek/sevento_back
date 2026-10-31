import django_filters

from .models import BillOfMaterials, ProductionOrder


class BillOfMaterialsFilter(django_filters.FilterSet):
    product = django_filters.NumberFilter(field_name="product_id")
    status = django_filters.ChoiceFilter(choices=BillOfMaterials.Status.choices)

    class Meta:
        model = BillOfMaterials
        fields = ["product", "status"]


class ProductionOrderFilter(django_filters.FilterSet):
    status = django_filters.ChoiceFilter(choices=ProductionOrder.Status.choices)
    branch = django_filters.NumberFilter(field_name="branch_id")
    product = django_filters.NumberFilter(field_name="product_id")

    class Meta:
        model = ProductionOrder
        fields = ["status", "branch", "product"]
