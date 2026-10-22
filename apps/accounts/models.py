from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.db import models

from core.models import TimeStampedModel

from .capabilities import CAPABILITY_CODES, validate_codes


class Role(TimeStampedModel):
    code = models.SlugField(max_length=50, unique=True)
    name = models.CharField(max_length=100)
    capabilities = models.JSONField(default=list, blank=True)
    is_system = models.BooleanField(default=False)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    def clean(self):
        unknown = validate_codes(self.capabilities or [])
        if unknown:
            raise ValidationError({"capabilities": f"Noma'lum huquqlar: {', '.join(unknown)}"})


class User(AbstractUser):
    first_name = None
    last_name = None

    full_name = models.CharField("F.I.O.", max_length=150)
    phone = models.CharField(max_length=30, blank=True)
    role = models.ForeignKey(
        Role, null=True, blank=True, on_delete=models.PROTECT, related_name="users"
    )
    branches = models.ManyToManyField(
        "branches.Branch", through="UserBranch", related_name="users", blank=True
    )

    REQUIRED_FIELDS = ["full_name"]

    class Meta:
        ordering = ["full_name", "username"]

    def __str__(self):
        return self.full_name or self.username

    # --- huquqlar (core duck-typing orqali shu ikki metodga tayanadi) ---

    def get_capabilities(self) -> frozenset[str]:
        cached = getattr(self, "_capabilities_cache", None)
        if cached is None:
            if self.is_superuser:
                cached = CAPABILITY_CODES
            elif self.role_id:
                cached = frozenset(self.role.capabilities or [])
            else:
                cached = frozenset()
            self._capabilities_cache = cached
        return cached

    def has_capability(self, code: str) -> bool:
        return self.is_active and code in self.get_capabilities()

    def accessible_branch_ids(self) -> frozenset[int] | None:
        """None = barcha nuqtalar; aks holda biriktirilgan nuqtalar to'plami."""
        if self.has_capability("branches.view_all"):
            return None
        cached = getattr(self, "_branch_ids_cache", None)
        if cached is None:
            cached = frozenset(self.branch_links.values_list("branch_id", flat=True))
            self._branch_ids_cache = cached
        return cached

    def invalidate_access_cache(self) -> None:
        self._capabilities_cache = None
        self._branch_ids_cache = None


class UserBranch(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="branch_links")
    branch = models.ForeignKey(
        "branches.Branch", on_delete=models.CASCADE, related_name="user_links"
    )
    is_default = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "branch"], name="uniq_user_branch"),
        ]

    def __str__(self):
        return f"{self.user_id} ↔ {self.branch_id}"
