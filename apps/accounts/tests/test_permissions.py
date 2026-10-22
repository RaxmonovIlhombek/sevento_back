import pytest

from apps.accounts.capabilities import CAPABILITY_CODES
from apps.accounts.models import User
from apps.accounts.selectors import get_realtime_groups
from core.api.permissions import HasCapability

pytestmark = pytest.mark.django_db


def test_role_capabilities(owner, seller, branch):
    assert owner.has_capability("users.manage")
    assert owner.accessible_branch_ids() is None
    assert not seller.has_capability("users.manage")
    assert seller.has_capability("sales.create")
    assert seller.accessible_branch_ids() == {branch.id}


def test_superuser_without_role_has_everything(db):
    user = User.objects.create_superuser(username="root", password="x", full_name="Root")
    assert user.get_capabilities() == CAPABILITY_CODES
    assert user.accessible_branch_ids() is None


def test_inactive_user_has_no_capabilities(seller):
    seller.is_active = False
    assert not seller.has_capability("sales.create")


def test_user_without_role(db):
    user = User.objects.create_user(username="norole", password="x", full_name="N")
    assert user.get_capabilities() == frozenset()
    assert user.accessible_branch_ids() == frozenset()


def test_realtime_groups(owner, seller, branch, branch2):
    assert get_realtime_groups(seller) == [
        f"user_{seller.id}",
        "role_seller",
        f"branch_{branch.id}",
        "broadcast",
    ]
    assert get_realtime_groups(owner) == [
        f"user_{owner.id}",
        "role_owner",
        f"branch_{branch.id}",
        f"branch_{branch2.id}",
        "broadcast",
    ]


class _View:
    def __init__(self, action=None, **attrs):
        self.action = action
        for k, v in attrs.items():
            setattr(self, k, v)


class _Request:
    def __init__(self, user, method="GET"):
        self.user = user
        self.method = method


def test_has_capability_with_map(owner, seller):
    view = _View("create", capability_map={"list": None, "create": "users.manage"})
    assert HasCapability().has_permission(_Request(owner), view)
    assert not HasCapability().has_permission(_Request(seller), view)
    assert HasCapability().has_permission(
        _Request(seller), _View("list", capability_map=view.capability_map)
    )
    # map da yo'q action → rad
    assert not HasCapability().has_permission(
        _Request(owner), _View("destroy", capability_map=view.capability_map)
    )
    # "*" fallback
    assert HasCapability().has_permission(
        _Request(owner), _View("destroy", capability_map={"*": "users.manage"})
    )
    # partial_update → update
    assert HasCapability().has_permission(
        _Request(owner), _View("partial_update", capability_map={"update": "users.manage"})
    )


def test_has_capability_with_required_attr(owner, seller):
    view = _View(required_capability="audit.view")
    assert HasCapability().has_permission(_Request(owner), view)
    assert not HasCapability().has_permission(_Request(seller), view)
