from django.contrib import admin

from .models import DocumentSequence, IdempotencyRecord, OutboxEvent, SystemSetting


@admin.register(OutboxEvent)
class OutboxEventAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "name",
        "aggregate_type",
        "aggregate_id",
        "status",
        "attempts",
        "occurred_at",
    )
    list_filter = ("status", "name")
    search_fields = ("name", "aggregate_id")
    readonly_fields = [f.name for f in OutboxEvent._meta.fields]
    ordering = ("-id",)

    def has_add_permission(self, request):
        return False


@admin.register(SystemSetting)
class SystemSettingAdmin(admin.ModelAdmin):
    list_display = ("key", "value", "updated_by", "updated_at")
    readonly_fields = ("updated_by", "created_at", "updated_at")


@admin.register(DocumentSequence)
class DocumentSequenceAdmin(admin.ModelAdmin):
    list_display = ("doc_type", "branch_id", "year", "last_number")


@admin.register(IdempotencyRecord)
class IdempotencyRecordAdmin(admin.ModelAdmin):
    list_display = ("key", "user", "method", "path", "response_status", "created_at")
    readonly_fields = [f.name for f in IdempotencyRecord._meta.fields]
