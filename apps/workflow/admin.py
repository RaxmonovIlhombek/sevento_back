from django.contrib import admin

from .models import ApprovalInstance, ApprovalRule, ApprovalStep


class ApprovalStepInline(admin.TabularInline):
    model = ApprovalStep
    extra = 0


@admin.register(ApprovalRule)
class ApprovalRuleAdmin(admin.ModelAdmin):
    list_display = ("entity_type", "sequence", "approver", "min_amount", "max_amount", "is_active")
    list_filter = ("entity_type", "is_active")
    search_fields = ("entity_type",)


@admin.register(ApprovalInstance)
class ApprovalInstanceAdmin(admin.ModelAdmin):
    list_display = ("entity_type", "entity_id", "status", "requested_by", "branch", "created_at")
    list_filter = ("status", "entity_type", "branch")
    search_fields = ("entity_type",)
    inlines = [ApprovalStepInline]
    readonly_fields = ("decided_at",)
