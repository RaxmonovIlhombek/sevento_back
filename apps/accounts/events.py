from dataclasses import dataclass, field
from typing import Any

from core.events import Event


@dataclass(frozen=True, kw_only=True)
class UserLoggedIn(Event):
    name = "user.logged_in"
    aggregate_type = "user"
    aggregate_id_field = "user_id"

    user_id: int
    username: str


@dataclass(frozen=True, kw_only=True)
class LoginFailed(Event):
    name = "user.login_failed"
    aggregate_type = "user"

    username: str
    reason: str  # bad_credentials | inactive


@dataclass(frozen=True, kw_only=True)
class UserCreated(Event):
    name = "user.created"
    aggregate_type = "user"
    aggregate_id_field = "user_id"

    user_id: int
    username: str
    role: str | None
    branch_ids: list[int] = field(default_factory=list)


@dataclass(frozen=True, kw_only=True)
class UserUpdated(Event):
    name = "user.updated"
    aggregate_type = "user"
    aggregate_id_field = "user_id"

    user_id: int
    username: str
    changes: dict[str, Any] = field(default_factory=dict)  # {maydon: {"old": .., "new": ..}}


@dataclass(frozen=True, kw_only=True)
class UserDeactivated(Event):
    name = "user.deactivated"
    aggregate_type = "user"
    aggregate_id_field = "user_id"

    user_id: int
    username: str


@dataclass(frozen=True, kw_only=True)
class UserPasswordChanged(Event):
    name = "user.password_changed"
    aggregate_type = "user"
    aggregate_id_field = "user_id"

    user_id: int
    by_self: bool


@dataclass(frozen=True, kw_only=True)
class RoleCreated(Event):
    name = "role.created"
    aggregate_type = "role"
    aggregate_id_field = "role_id"

    role_id: int
    code: str
    capabilities: list[str] = field(default_factory=list)


@dataclass(frozen=True, kw_only=True)
class RoleUpdated(Event):
    name = "role.updated"
    aggregate_type = "role"
    aggregate_id_field = "role_id"

    role_id: int
    code: str
    changes: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, kw_only=True)
class RoleDeleted(Event):
    name = "role.deleted"
    aggregate_type = "role"
    aggregate_id_field = "role_id"

    role_id: int
    code: str
