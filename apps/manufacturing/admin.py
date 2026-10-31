from django.contrib import admin

from .models import BOMItem, BillOfMaterials, ProductionOrder


class BOMItemInline(admin.TabularInline):
    model = BOMItem
    extra = 0


@admin.register(BillOfMaterials)
class BillOfMaterialsAdmin(admin.ModelAdmin):
    list_display = ("name", "product", "version", "status", "quantity")
    list_filter = ("status",)
    search_fields = ("name", "product__name")
    inlines = [BOMItemInline]


@admin.register(ProductionOrder)
class ProductionOrderAdmin(admin.ModelAdmin):
    list_display = ("number", "product", "quantity", "status", "branch", "planned_start")
    list_filter = ("status", "branch")
    search_fields = ("number", "product__name")
    readonly_fields = ("actual_start", "actual_end")
