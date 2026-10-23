import django_filters

from . import selectors
from .models import Product


class ProductFilter(django_filters.FilterSet):
    category = django_filters.NumberFilter(method="filter_category")
    search = django_filters.CharFilter(method="filter_search")

    class Meta:
        model = Product
        fields = ["category", "unit", "is_active"]

    def filter_category(self, queryset, name, value):
        """Kategoriya va uning barcha avlodlari."""
        return queryset.filter(category_id__in=selectors.descendant_ids(int(value)))

    def filter_search(self, queryset, name, value):
        return selectors.search_products(queryset, value)
