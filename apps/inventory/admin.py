from django.contrib import admin

from .models import Batch, StockLevel, StockMovement


class ReadOnlyAdmin(admin.ModelAdmin):
    """Qoldiq faqat service orqali o'zgaradi — admin panelda faqat ko'rish."""

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(StockLevel)
class StockLevelAdmin(ReadOnlyAdmin):
    list_display = ("branch", "product", "quantity", "min_quantity", "below_minimum", "updated_at")
    list_filter = ("branch", "below_minimum")
    search_fields = ("product__name", "product__sku")


@admin.register(Batch)
class BatchAdmin(ReadOnlyAdmin):
    list_display = (
        "id",
        "branch",
        "product",
        "source_type",
        "source_number",
        "received_at",
        "quantity_initial",
        "quantity_remaining",
        "unit_cost_base",
    )
    list_filter = ("branch", "source_type")
    search_fields = ("product__name", "source_number")


@admin.register(StockMovement)
class StockMovementAdmin(ReadOnlyAdmin):
    list_display = (
        "created_at",
        "branch",
        "product",
        "type",
        "quantity",
        "balance_after",
        "document_type",
        "document_number",
    )
    list_filter = ("type", "branch")
    search_fields = ("product__name", "document_number")
