from django.contrib import admin

from .models import PayrollRun, Payslip


class PayslipInline(admin.TabularInline):
    model = Payslip
    extra = 0


@admin.register(PayrollRun)
class PayrollRunAdmin(admin.ModelAdmin):
    list_display = ("period_start", "period_end", "branch", "status", "total_gross", "total_net")
    list_filter = ("status", "branch")
    inlines = [PayslipInline]


@admin.register(Payslip)
class PayslipAdmin(admin.ModelAdmin):
    list_display = ("run", "employee", "gross", "net")
    list_filter = ("run",)
