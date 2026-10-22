"""Nuqta (branch) chegarasi yordamchilari.

Foydalanuvchi ob'ekti ikki metodni ta'minlaydi (apps.accounts.User):
  - has_capability(code) -> bool
  - accessible_branch_ids() -> set[int] | None   (None = barcha nuqtalar)
core ularni duck-typing orqali ishlatadi, accounts ni import qilmaydi.
"""

from .exceptions import BranchForbidden


def can_access_branch(user, branch_id: int | None) -> bool:
    if branch_id is None:
        return True
    ids = user.accessible_branch_ids()
    return ids is None or branch_id in ids


def ensure_branch_access(user, branch_id: int | None) -> None:
    """Service lar yozishdan oldin chaqiradi: begona nuqta → 403 branch_forbidden."""
    if not can_access_branch(user, branch_id):
        raise BranchForbidden()


def scope_queryset_to_user(queryset, user, branch_field: str = "branch"):
    """O'qish uchun: faqat foydalanuvchi ko'ra oladigan nuqtalar qoldiriladi."""
    ids = user.accessible_branch_ids()
    if ids is None:
        return queryset
    lookup = "pk__in" if branch_field in ("pk", "id") else f"{branch_field}__in"
    return queryset.filter(**{lookup: ids})
