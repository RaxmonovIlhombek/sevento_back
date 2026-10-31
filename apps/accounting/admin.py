from django.contrib import admin

from .models import Account, FiscalPeriod, FiscalYear, JournalEntry, JournalLine


@admin.register(Account)
class AccountAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "account_type", "normal_balance", "parent", "is_active", "is_postable")
    list_filter = ("account_type", "is_active", "is_postable")
    search_fields = ("code", "name")
    ordering = ("code",)


@admin.register(FiscalYear)
class FiscalYearAdmin(admin.ModelAdmin):
    list_display = ("year", "start_date", "end_date", "is_closed")


@admin.register(FiscalPeriod)
class FiscalPeriodAdmin(admin.ModelAdmin):
    list_display = ("fiscal_year", "number", "start_date", "end_date", "is_closed")
    list_filter = ("fiscal_year", "is_closed")


class JournalLineInline(admin.TabularInline):
    model = JournalLine
    extra = 0


@admin.register(JournalEntry)
class JournalEntryAdmin(admin.ModelAdmin):
    list_display = ("number", "date", "fiscal_period", "branch", "status", "created_by")
    list_filter = ("status", "fiscal_period__fiscal_year")
    search_fields = ("number", "description")
    inlines = [JournalLineInline]
    readonly_fields = ("posted_at", "posted_by", "reversed_by_entry")
