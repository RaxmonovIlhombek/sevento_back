from django.contrib import admin

from .models import Currency, ExchangeRate


@admin.register(Currency)
class CurrencyAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "symbol", "decimal_places", "is_active", "sort_order")
    list_filter = ("is_active",)


@admin.register(ExchangeRate)
class ExchangeRateAdmin(admin.ModelAdmin):
    list_display = ("currency", "rate", "date", "source", "created_by", "updated_at")
    list_filter = ("currency", "source")
    date_hierarchy = "date"
