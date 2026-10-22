import django_filters


class DateRangeFilterSet(django_filters.FilterSet):
    """?date_from=2026-10-01&date_to=2026-10-31 — `date_field` bo'yicha (mahalliy sana)."""

    date_field = "created_at"

    date_from = django_filters.DateFilter(method="filter_date_from")
    date_to = django_filters.DateFilter(method="filter_date_to")

    def filter_date_from(self, queryset, name, value):
        return queryset.filter(**{f"{self.date_field}__date__gte": value})

    def filter_date_to(self, queryset, name, value):
        return queryset.filter(**{f"{self.date_field}__date__lte": value})
