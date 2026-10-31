from django.conf import settings
from django.db import models

from core.models import TimeStampedModel


class Department(TimeStampedModel):
    name = models.CharField(max_length=200)
    parent = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.PROTECT, related_name="children"
    )
    branch = models.ForeignKey(
        "branches.Branch", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Position(TimeStampedModel):
    name = models.CharField(max_length=200)
    department = models.ForeignKey(Department, on_delete=models.PROTECT, related_name="positions")
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Employee(TimeStampedModel):
    class Status(models.TextChoices):
        ACTIVE = "active", "Faol"
        ON_LEAVE = "on_leave", "Ta'tilda"
        TERMINATED = "terminated", "Ishdan bo'shatilgan"

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="employee_profile"
    )
    employee_number = models.CharField(max_length=40, unique=True)
    department = models.ForeignKey(Department, on_delete=models.PROTECT, related_name="employees")
    position = models.ForeignKey(Position, on_delete=models.PROTECT, related_name="employees")
    branch = models.ForeignKey(
        "branches.Branch", on_delete=models.PROTECT, related_name="+"
    )
    hire_date = models.DateField()
    termination_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.ACTIVE)
    base_salary = models.DecimalField(max_digits=20, decimal_places=4, default=0)
    phone = models.CharField(max_length=30, blank=True)
    address = models.TextField(blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["employee_number"]

    def __str__(self):
        return f"{self.employee_number} — {self.user}"
