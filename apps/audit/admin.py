from django.contrib import admin

from .models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "event_name",
        "actor",
        "branch",
        "aggregate_type",
        "aggregate_id",
        "created_at",
    )
    list_filter = ("event_name",)
    search_fields = ("actor__username", "request_id")
    readonly_fields = [f.name for f in AuditLog._meta.fields]
    ordering = ("-id",)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
