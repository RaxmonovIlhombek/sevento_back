"""Foydalanuvchi, rol va autentifikatsiya biznes mantig'i (yozish)."""

from django.contrib.auth import authenticate
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken

from core.exceptions import BusinessRuleError

from . import events
from .capabilities import validate_codes
from .models import Role, User, UserBranch

# --- autentifikatsiya ---


def authenticate_user(*, username: str, password: str) -> User:
    user = authenticate(username=username, password=password)
    if user is None:
        with transaction.atomic():
            reason = (
                "inactive"
                if User.objects.filter(username=username, is_active=False).exists()
                else "bad_credentials"
            )
            events.LoginFailed.publish_from(username=username[:150], reason=reason)
        raise AuthenticationFailed(code="authentication_failed")
    with transaction.atomic():
        User.objects.filter(pk=user.pk).update(last_login=timezone.now())
        events.UserLoggedIn.publish_from(actor=user, user_id=user.pk, username=user.username)
    return user


def issue_tokens(user: User) -> tuple[str, str]:
    """(access, refresh) juftligi."""
    refresh = RefreshToken.for_user(user)
    return str(refresh.access_token), str(refresh)


def rotate_refresh_token(raw_refresh: str) -> tuple[str, str]:
    """Eski refresh qora ro'yxatga, yangi (access, refresh) qaytariladi. Yaroqsiz → TokenError."""
    token = RefreshToken(raw_refresh)  # imzo, muddat, qora ro'yxat tekshiriladi
    user = User.objects.filter(pk=token.get("user_id")).first()
    if user is None or not user.is_active:
        raise TokenError("Foydalanuvchi faol emas")
    token.blacklist()
    token.set_jti()
    token.set_exp()
    token.set_iat()
    return str(token.access_token), str(token)


def revoke_refresh_token(raw_refresh: str | None) -> None:
    if not raw_refresh:
        return
    try:
        RefreshToken(raw_refresh).blacklist()
    except TokenError:
        pass


# --- foydalanuvchilar ---


def _set_branches(user: User, branch_ids: list[int] | None, default_branch_id: int | None) -> None:
    if branch_ids is None:
        return
    user.branch_links.all().delete()
    UserBranch.objects.bulk_create(
        [
            UserBranch(user=user, branch_id=bid, is_default=(bid == default_branch_id))
            for bid in dict.fromkeys(branch_ids)
        ]
    )
    user.invalidate_access_cache()


def create_user(
    *,
    actor: User,
    username: str,
    password: str,
    full_name: str,
    role: Role | None,
    phone: str = "",
    branch_ids: list[int] | None = None,
    default_branch_id: int | None = None,
    is_active: bool = True,
) -> User:
    with transaction.atomic():
        user = User(
            username=username, full_name=full_name, phone=phone, role=role, is_active=is_active
        )
        user.set_password(password)
        user.save()
        _set_branches(user, branch_ids or [], default_branch_id)
        events.UserCreated.publish_from(
            actor=actor,
            user_id=user.pk,
            username=user.username,
            role=role.code if role else None,
            branch_ids=sorted(set(branch_ids or [])),
        )
    return user


TRACKED_USER_FIELDS = ("username", "full_name", "phone", "is_active", "role_id")


def update_user(
    *,
    actor: User,
    user: User,
    branch_ids: list[int] | None = None,
    default_branch_id: int | None = None,
    password: str | None = None,
    **fields,
) -> User:
    if "role" in fields:
        fields["role_id"] = fields.pop("role").pk if fields["role"] else None
    with transaction.atomic():
        before = {f: getattr(user, f) for f in TRACKED_USER_FIELDS}
        before_branches = sorted(user.branch_links.values_list("branch_id", flat=True))
        for name, value in fields.items():
            setattr(user, name, value)
        if password:
            user.set_password(password)
        user.save()
        _set_branches(user, branch_ids, default_branch_id)

        changes = {
            f: {"old": before[f], "new": getattr(user, f)}
            for f in TRACKED_USER_FIELDS
            if before[f] != getattr(user, f)
        }
        after_branches = sorted(user.branch_links.values_list("branch_id", flat=True))
        if branch_ids is not None and before_branches != after_branches:
            changes["branch_ids"] = {"old": before_branches, "new": after_branches}
        if password:
            changes["password"] = {"old": "***", "new": "***"}

        if changes:
            events.UserUpdated.publish_from(
                actor=actor, user_id=user.pk, username=user.username, changes=changes
            )
        if "is_active" in changes and not user.is_active:
            events.UserDeactivated.publish_from(
                actor=actor, user_id=user.pk, username=user.username
            )
    return user


def change_password(*, actor: User, user: User, new_password: str) -> None:
    with transaction.atomic():
        user.set_password(new_password)
        user.save(update_fields=["password"])
        events.UserPasswordChanged.publish_from(
            actor=actor, user_id=user.pk, by_self=(actor.pk == user.pk)
        )


# --- rollar ---


def _check_capabilities(capabilities: list[str]) -> None:
    unknown = validate_codes(capabilities)
    if unknown:
        raise BusinessRuleError(
            f"Noma'lum huquqlar: {', '.join(unknown)}",
            code="unknown_capability",
            status_code=400,
            details=[
                {"field": "capabilities", "code": "unknown_capability", "message": c}
                for c in unknown
            ],
        )


def create_role(*, actor: User, code: str, name: str, capabilities: list[str]) -> Role:
    _check_capabilities(capabilities)
    with transaction.atomic():
        role = Role.objects.create(code=code, name=name, capabilities=sorted(set(capabilities)))
        events.RoleCreated.publish_from(
            actor=actor, role_id=role.pk, code=role.code, capabilities=role.capabilities
        )
    return role


def update_role(*, actor: User, role: Role, **fields) -> Role:
    if "capabilities" in fields:
        _check_capabilities(fields["capabilities"])
        fields["capabilities"] = sorted(set(fields["capabilities"]))
    if role.is_system and "code" in fields and fields["code"] != role.code:
        raise BusinessRuleError("Tizim rolining kodini o'zgartirib bo'lmaydi", code="system_role")
    with transaction.atomic():
        changes = {}
        for name, value in fields.items():
            old = getattr(role, name)
            if old != value:
                changes[name] = {"old": old, "new": value}
                setattr(role, name, value)
        role.save()
        if changes:
            events.RoleUpdated.publish_from(
                actor=actor, role_id=role.pk, code=role.code, changes=changes
            )
    return role


def delete_role(*, actor: User, role: Role) -> None:
    if role.is_system:
        raise BusinessRuleError("Tizim rolini o'chirib bo'lmaydi", code="system_role")
    if role.users.exists():
        raise BusinessRuleError("Bu rolga foydalanuvchilar biriktirilgan", code="role_in_use")
    with transaction.atomic():
        events.RoleDeleted.publish_from(actor=actor, role_id=role.pk, code=role.code)
        role.delete()


def ensure_preset_roles() -> int:
    """Boshlang'ich rollarni yaratadi (mavjudlarini o'zgartirmaydi); yaratilganlar soni."""
    from .capabilities import ROLE_PRESETS

    created = 0
    for code, preset in ROLE_PRESETS.items():
        _, was_created = Role.objects.get_or_create(
            code=code,
            defaults={
                "name": preset["name"],
                "capabilities": preset["capabilities"],
                "is_system": True,
            },
        )
        created += int(was_created)
    return created
