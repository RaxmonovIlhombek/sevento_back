from django.conf import settings
from django.db import models

from core.models import TimeStampedModel


class PayrollRun(TimeStampedModel):
    class Status(models.TextChoices):
        DRAFT = "draft", "Qoralama"
        CALCULATED = "calculated", "Hisoblandi"
        PAID = "paid", "To'landi"
        CANCELLED = "cancelled", "Bekor qilindi"

    period_start = models.DateField()
    period_end = models.DateField()
    branch = models.ForeignKey("branches.Branch", on_delete=models.PROTECT, related_name="+")
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.DRAFT)
    total_gross = models.DecimalField(max_digits=20, decimal_places=4, default=0)
    total_net = models.DecimalField(max_digits=20, decimal_places=4, default=0)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    paid_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-period_end"]

    def __str__(self):
        return f"Payroll {self.period_start}..{self.period_end}"


class Payslip(TimeStampedModel):
    run = models.ForeignKey(PayrollRun, on_delete=models.CASCADE, related_name="payslips")
    employee = models.ForeignKey("hr.Employee", on_delete=models.PROTECT, related_name="payslips")
    base_salary = models.DecimalField(max_digits=20, decimal_places=4, default=0)
    bonus = models.DecimalField(max_digits=20, decimal_places=4, default=0)
    allowance = models.DecimalField(max_digits=20, decimal_places=4, default=0)
    deduction = models.DecimalField(max_digits=20, decimal_places=4, default=0)
    tax = models.DecimalField(max_digits=20, decimal_places=4, default=0)
    gross = models.DecimalField(max_digits=20, decimal_places=4, default=0)
    net = models.DecimalField(max_digits=20, decimal_places=4, default=0)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["employee__employee_number"]
        constraints = [
            models.UniqueConstraint(fields=["run", "employee"], name="uniq_payslip_run_employee")
        ]

    def __str__(self):
        return f"{self.run_id} — {self.employee_id}"
