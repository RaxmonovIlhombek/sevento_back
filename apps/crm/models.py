from django.conf import settings
from django.db import models

from core.models import TimeStampedModel


class Lead(TimeStampedModel):
    class Status(models.TextChoices):
        NEW = "new", "Yangi"
        CONTACTED = "contacted", "Aloqa qilindi"
        QUALIFIED = "qualified", "Malakali"
        LOST = "lost", "Yo'qotildi"
        CONVERTED = "converted", "Mijozga aylantirildi"

    name = models.CharField(max_length=200)
    company = models.CharField(max_length=200, blank=True)
    phone = models.CharField(max_length=30, blank=True)
    email = models.EmailField(blank=True)
    source = models.CharField(max_length=100, blank=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.NEW)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    branch = models.ForeignKey(
        "branches.Branch", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.name


class Deal(TimeStampedModel):
    class Stage(models.TextChoices):
        PROSPECTING = "prospecting", "Izlash"
        QUALIFICATION = "qualification", "Malakalash"
        PROPOSAL = "proposal", "Taklif"
        NEGOTIATION = "negotiation", "Muzokara"
        WON = "won", "Yutildi"
        LOST = "lost", "Yo'qotildi"

    name = models.CharField(max_length=200)
    lead = models.ForeignKey(Lead, null=True, blank=True, on_delete=models.SET_NULL, related_name="deals")
    customer = models.ForeignKey(
        "payments.Customer", null=True, blank=True, on_delete=models.SET_NULL, related_name="deals"
    )
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    branch = models.ForeignKey(
        "branches.Branch", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    stage = models.CharField(max_length=16, choices=Stage.choices, default=Stage.PROSPECTING)
    amount = models.DecimalField(max_digits=20, decimal_places=4, default=0)
    currency = models.ForeignKey(
        "currency.Currency", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    expected_close_date = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.name


class Activity(TimeStampedModel):
    class Type(models.TextChoices):
        CALL = "call", "Qo'ng'iroq"
        EMAIL = "email", "Email"
        MEETING = "meeting", "Uchrashuv"
        NOTE = "note", "Eslatma"
        TASK = "task", "Vazifa"

    activity_type = models.CharField(max_length=10, choices=Type.choices, default=Type.NOTE)
    subject = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    due_date = models.DateTimeField(null=True, blank=True)
    completed = models.BooleanField(default=False)
    lead = models.ForeignKey(Lead, null=True, blank=True, on_delete=models.CASCADE, related_name="activities")
    deal = models.ForeignKey(Deal, null=True, blank=True, on_delete=models.CASCADE, related_name="activities")
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.subject
