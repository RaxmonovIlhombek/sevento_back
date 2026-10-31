from django.contrib import admin

from .models import Activity, Deal, Lead


@admin.register(Lead)
class LeadAdmin(admin.ModelAdmin):
    list_display = ("name", "company", "status", "owner", "branch", "created_at")
    list_filter = ("status", "branch")
    search_fields = ("name", "company", "phone", "email")


@admin.register(Deal)
class DealAdmin(admin.ModelAdmin):
    list_display = ("name", "stage", "amount", "owner", "branch", "expected_close_date")
    list_filter = ("stage", "branch")
    search_fields = ("name",)


@admin.register(Activity)
class ActivityAdmin(admin.ModelAdmin):
    list_display = ("subject", "activity_type", "completed", "due_date", "owner")
    list_filter = ("activity_type", "completed")
    search_fields = ("subject",)
