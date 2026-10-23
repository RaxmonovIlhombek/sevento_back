from rest_framework.permissions import IsAuthenticated

from ..access import scope_queryset_to_user
from .permissions import HasCapability


class CapabilityViewSetMixin:
    """ViewSet: capability_map = {"list": "x.view", "create": "x.manage", ...}."""

    permission_classes = [IsAuthenticated, HasCapability]
    capability_map: dict[str, str | tuple[str, ...] | None] = {}


class BranchScopedQuerySetMixin:
    """get_queryset() ni foydalanuvchi ko'ra oladigan nuqtalar bilan cheklaydi.

    `branch_field` — modeldagi nuqta FK nomi; Branch modelining o'zi uchun "pk".
    Begona nuqta ob'ekti so'ralsa 404 (mavjudligini ham oshkor qilmaymiz).
    """

    branch_field = "branch"

    def get_queryset(self):
        queryset = super().get_queryset()
        return scope_queryset_to_user(queryset, self.request.user, self.branch_field)
