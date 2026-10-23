from django.contrib import admin

from .models import ExpenseType, Purchase, PurchaseExpense, PurchaseItem, Supplier


@admin.register(Supplier)
class SupplierAdmin(admin.ModelAdmin):
    list_display = ("name", "phone", "contact_person", "tin", "is_active")
    search_fields = ("name", "phone", "tin")
    list_filter = ("is_active",)


@admin.register(ExpenseType)
class ExpenseTypeAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "default_allocation", "is_active")


class PurchaseItemInline(admin.TabularInline):
    model = PurchaseItem
    extra = 0
    can_delete = False
    readonly_fields = [f.name for f in PurchaseItem._meta.fields]

    def has_add_permission(self, request, obj=None):
        return False


class PurchaseExpenseInline(admin.TabularInline):
    model = PurchaseExpense
    extra = 0
    can_delete = False
    readonly_fields = [f.name for f in PurchaseExpense._meta.fields]

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Purchase)
class PurchaseAdmin(admin.ModelAdmin):
    """Kirim faqat API (service) orqali qabul/bekor qilinadi — admin panelda faqat ko'rish."""

    list_display = (
        "number",
        "branch",
        "supplier",
        "status",
        "currency",
        "subtotal",
        "total_base",
        "created_at",
    )
    list_filter = ("status", "branch", "currency")
    search_fields = ("number", "invoice_number", "supplier__name")
    inlines = [PurchaseItemInline, PurchaseExpenseInline]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
