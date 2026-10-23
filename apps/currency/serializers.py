from rest_framework import serializers

from . import selectors
from .models import Currency, ExchangeRate


class CurrencySerializer(serializers.ModelSerializer):
    is_base = serializers.SerializerMethodField()

    class Meta:
        model = Currency
        fields = [
            "id",
            "code",
            "name",
            "symbol",
            "decimal_places",
            "is_active",
            "sort_order",
            "is_base",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at"]
        extra_kwargs = {"code": {"validators": []}}

    def get_is_base(self, currency) -> bool:
        """Tannarx, foyda va kredit limiti shu valyutada (sozlama currency.base_code)."""
        return currency.code == selectors.base_currency_code()

    def validate_code(self, value):
        value = value.strip().upper()
        if len(value) != 3 or not value.isalpha():
            raise serializers.ValidationError("3 ta lotin harfi (ISO 4217)", code="invalid")
        qs = Currency.objects.filter(code=value)
        if self.instance is not None:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("Bu valyuta allaqachon bor", code="unique")
        return value

    def validate_decimal_places(self, value):
        if value > 4:
            raise serializers.ValidationError("Ko'pi bilan 4", code="max_value")
        return value


class ExchangeRateSerializer(serializers.ModelSerializer):
    currency_code = serializers.CharField(source="currency.code", read_only=True)
    created_by_name = serializers.CharField(
        source="created_by.full_name", read_only=True, default=None, allow_null=True
    )

    class Meta:
        model = ExchangeRate
        fields = [
            "id",
            "currency",
            "currency_code",
            "rate",
            "date",
            "source",
            "created_by",
            "created_by_name",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class RateCreateSerializer(serializers.Serializer):
    currency = serializers.PrimaryKeyRelatedField(queryset=Currency.objects.filter(is_active=True))
    rate = serializers.DecimalField(max_digits=20, decimal_places=6, min_value=0)
    date = serializers.DateField(required=False)


class LatestRateSerializer(serializers.Serializer):
    currency = serializers.IntegerField()
    code = serializers.CharField()
    name = serializers.CharField()
    symbol = serializers.CharField()
    decimal_places = serializers.IntegerField()
    rate = serializers.DecimalField(max_digits=20, decimal_places=6, allow_null=True)
    date = serializers.DateField(allow_null=True)
    source = serializers.CharField(allow_null=True)


class FetchResultSerializer(serializers.Serializer):
    provider = serializers.CharField()
    updated = ExchangeRateSerializer(many=True)
