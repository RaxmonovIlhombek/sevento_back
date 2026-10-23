from django.db.models import Count, Prefetch, QuerySet

from apps.branches import selectors as branch_selectors

from .capabilities import CAPABILITIES
from .models import Role, User, UserBranch


def users_queryset() -> QuerySet[User]:
    return User.objects.select_related("role").prefetch_related(
        Prefetch("branch_links", queryset=UserBranch.objects.select_related("branch"))
    )


def roles_queryset() -> QuerySet[Role]:
    return Role.objects.annotate(users_count=Count("users"))


def get_user(user_id: int) -> User | None:
    """Rol bilan birga (huquqlar uchun). Boshqa app lar User modelini to'g'ridan-to'g'ri olmaydi."""
    return User.objects.select_related("role").filter(pk=user_id).first()


def is_user_active(user_id: int) -> bool:
    return User.objects.filter(pk=user_id, is_active=True).exists()


def get_user_branch_ids(user: User) -> frozenset[int] | None:
    return user.accessible_branch_ids()


def user_branches(user: User) -> list[dict]:
    """Nuqta tanlagich uchun: hamma nuqtani ko'ra olsa — barcha faol nuqtalar."""
    if user.accessible_branch_ids() is None:
        return [
            {"id": b.id, "code": b.code, "name": b.name, "type": b.type, "is_default": False}
            for b in branch_selectors.active_branches()
        ]
    links = user.branch_links.select_related("branch").order_by("branch__name")
    return [
        {
            "id": link.branch.id,
            "code": link.branch.code,
            "name": link.branch.name,
            "type": link.branch.type,
            "is_default": link.is_default,
        }
        for link in links
        if link.branch.is_active
    ]


def me_payload(user: User) -> dict:
    return {
        "id": user.id,
        "username": user.username,
        "full_name": user.full_name,
        "phone": user.phone,
        "is_superuser": user.is_superuser,
        "role": {"code": user.role.code, "name": user.role.name} if user.role_id else None,
        "capabilities": sorted(user.get_capabilities()),
        "branches": user_branches(user),
        "all_branches": user.accessible_branch_ids() is None,
    }


def capabilities_payload() -> list[dict]:
    return [{"code": c.code, "name": c.name, "group": c.group} for c in CAPABILITIES]


def get_realtime_groups(user: User) -> list[str]:
    """WebSocket guruhlari: user_{id}, role_{code}, branch_{id}... (realtime.md)."""
    groups = [f"user_{user.id}"]
    if user.role_id:
        groups.append(f"role_{user.role.code}")
    ids = user.accessible_branch_ids()
    if ids is None:
        ids = [b.id for b in branch_selectors.active_branches()]
    groups.extend(f"branch_{i}" for i in sorted(ids))
    groups.append("broadcast")  # hammaga: kurs yangilandi, tizim xabari
    return groups


def users_with_capability(code: str) -> QuerySet[User]:
    """Shu huquqqa ega faol foydalanuvchilar (bildirishnomalar uchun)."""
    return User.objects.filter(is_active=True).filter(Q_superuser_or_role_has(code))


def Q_superuser_or_role_has(code: str):
    from django.db.models import Q

    return Q(is_superuser=True) | Q(role__capabilities__contains=[code])
