from django.contrib import admin

from .models import Cashbox, CashFlowCategory, CashTransaction, Payment, PaymentMethod


@admin.register(PaymentMethod)
class PaymentMethodAdmin(admin.ModelAdmin):
    list_display = ["code", "name", "provider", "is_cash", "is_active", "sort_order"]


@admin.register(CashFlowCategory)
class CashFlowCategoryAdmin(admin.ModelAdmin):
    list_display = ["code", "name", "direction"]


class ReadOnlyAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Cashbox)
class CashboxAdmin(ReadOnlyAdmin):
    list_display = ["name", "branch", "currency", "balance", "is_active"]


@admin.register(Payment)
class PaymentAdmin(ReadOnlyAdmin):
    list_display = ["number", "kind", "method", "amount", "currency", "status", "received_at"]
    list_filter = ["kind", "status", "method"]
    search_fields = ["number", "document_number"]


@admin.register(CashTransaction)
class CashTransactionAdmin(ReadOnlyAdmin):
    list_display = ["cashbox", "direction", "category", "amount", "balance_after", "created_at"]
    list_filter = ["direction", "category"]
