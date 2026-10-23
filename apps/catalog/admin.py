from django.contrib import admin

from .models import Category, PriceType, Product, ProductPrice, Unit


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "parent", "sort_order", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name",)


@admin.register(Unit)
class UnitAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "decimal_places", "is_active")


@admin.register(PriceType)
class PriceTypeAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "is_default", "sort_order")


class ProductPriceInline(admin.TabularInline):
    model = ProductPrice
    extra = 0
    readonly_fields = ("created_by", "created_at")


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("sku", "name", "category", "unit", "is_active")
    list_filter = ("is_active", "category", "unit")
    search_fields = ("sku", "name", "barcode")
    inlines = [ProductPriceInline]
