import django_filters
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from core import settings_service
from core.api.filters import DateRangeFilterSet
from core.api.mixins import CapabilityViewSetMixin

from . import selectors, services
from .models import QUOTE_CODE, Currency, ExchangeRate
from .serializers import (
    CurrencySerializer,
    ExchangeRateSerializer,
    FetchResultSerializer,
    LatestRateSerializer,
    RateCreateSerializer,
)


@extend_schema(tags=["currency"])
class CurrencyViewSet(
    CapabilityViewSetMixin,
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    mixins.ListModelMixin,
    viewsets.GenericViewSet,
):
    """Valyutalar jadvali. Ro'yxat hammaga; o'zgartirish — settings.manage."""

    queryset = Currency.objects.all()
    serializer_class = CurrencySerializer
    capability_map = {
        "list": None,
        "retrieve": None,
        "create": "settings.manage",
        "update": "settings.manage",
    }
    filterset_fields = ["is_active"]
    ordering = ["sort_order", "code"]
    pagination_class = None

    def perform_create(self, serializer):
        serializer.instance = services.create_currency(
            actor=self.request.user, **serializer.validated_data
        )

    def perform_update(self, serializer):
        serializer.instance = services.update_currency(
            actor=self.request.user, currency=serializer.instance, **serializer.validated_data
        )


class ExchangeRateFilter(DateRangeFilterSet):
    date_field = "date"
    currency = django_filters.NumberFilter(field_name="currency_id")
    code = django_filters.CharFilter(field_name="currency__code", lookup_expr="iexact")

    class Meta:
        model = ExchangeRate
        fields = ["currency", "code", "source"]

    # DateRangeFilterSet __date lookup DateTimeField uchun; bu yerda DateField
    def filter_date_from(self, queryset, name, value):
        return queryset.filter(date__gte=value)

    def filter_date_to(self, queryset, name, value):
        return queryset.filter(date__lte=value)


@extend_schema(tags=["currency"])
class ExchangeRateViewSet(
    CapabilityViewSetMixin,
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    viewsets.GenericViewSet,
):
    """Kurslar tarixi; qo'lda kiritish va provayderdan yangilash — currency.rates.manage."""

    queryset = ExchangeRate.objects.none()
    serializer_class = ExchangeRateSerializer
    capability_map = {
        "list": None,
        "latest": None,
        "create": "currency.rates.manage",
        "fetch": "currency.rates.manage",
    }
    filterset_class = ExchangeRateFilter
    ordering_fields = ["date", "rate"]
    ordering = ["-date", "-id"]

    def get_queryset(self):
        return selectors.rates_queryset()

    @extend_schema(request=RateCreateSerializer, responses={201: ExchangeRateSerializer})
    def create(self, request, *args, **kwargs):
        serializer = RateCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        row = services.set_rate(
            actor=request.user, currency=data["currency"], rate=data["rate"], day=data.get("date")
        )
        row = selectors.rates_queryset().get(pk=row.pk)
        return Response(ExchangeRateSerializer(row).data, status=status.HTTP_201_CREATED)

    @extend_schema(responses=LatestRateSerializer(many=True))
    @action(detail=False, methods=["get"], pagination_class=None)
    def latest(self, request):
        """Har faol valyuta uchun joriy kurs (UZS dan tashqari)."""
        rows = []
        for currency in selectors.active_currencies().exclude(code=QUOTE_CODE):
            rate = selectors.latest_rate(currency)
            rows.append(
                {
                    "currency": currency.id,
                    "code": currency.code,
                    "name": currency.name,
                    "symbol": currency.symbol,
                    "decimal_places": currency.decimal_places,
                    "rate": rate.rate if rate else None,
                    "date": rate.date if rate else None,
                    "source": rate.source if rate else None,
                }
            )
        return Response(LatestRateSerializer(rows, many=True).data)

    @extend_schema(request=None, responses=FetchResultSerializer)
    @action(detail=False, methods=["post"])
    def fetch(self, request):
        """Tanlangan manbadan (sozlama currency.rate_provider) hozir yangilash."""
        rows = services.fetch_rates(actor=request.user)
        ids = [r.pk for r in rows]
        data = {
            "provider": str(settings_service.get("currency.rate_provider")),
            "updated": selectors.rates_queryset().filter(pk__in=ids),
        }
        return Response(FetchResultSerializer(data).data)
