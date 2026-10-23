"""Umumiy test fixture lari: rollar, foydalanuvchilar, nuqtalar, autentifikatsiyalangan mijoz."""

import pytest
from django.core.cache import cache
from rest_framework.test import APIClient

from apps.accounts.capabilities import ROLE_PRESETS
from apps.accounts.models import Role, User, UserBranch
from apps.branches.models import Branch


@pytest.fixture(autouse=True)
def _isolated_cache():
    """Sozlamalar va ticketlar keshda — testlar bir-biriga ta'sir qilmasin."""
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def roles(db) -> dict[str, Role]:
    """Tizim rollari (migratsiya seed qiladi; bo'lmasa yaratiladi)."""
    return {
        code: Role.objects.get_or_create(
            code=code,
            defaults={
                "name": preset["name"],
                "capabilities": preset["capabilities"],
                "is_system": True,
            },
        )[0]
        for code, preset in ROLE_PRESETS.items()
    }


@pytest.fixture
def branch(db) -> Branch:
    return Branch.objects.create(code="TSH1", name="Toshkent 1", type="shop")


@pytest.fixture
def branch2(db) -> Branch:
    return Branch.objects.create(code="SAM1", name="Samarqand 1", type="warehouse")


def _make_user(roles, code, username, branches=()):
    user = User.objects.create_user(
        username=username, password="parol12345", full_name=username.title(), role=roles[code]
    )
    for i, b in enumerate(branches):
        UserBranch.objects.create(user=user, branch=b, is_default=(i == 0))
    return user


@pytest.fixture
def owner(roles) -> User:
    return _make_user(roles, "owner", "rahbar")


@pytest.fixture
def accountant(roles) -> User:
    return _make_user(roles, "accountant", "buxgalter")


@pytest.fixture
def storekeeper(roles, branch) -> User:
    return _make_user(roles, "storekeeper", "omborchi", [branch])


@pytest.fixture
def seller(roles, branch) -> User:
    return _make_user(roles, "seller", "sotuvchi", [branch])


@pytest.fixture
def api_client() -> APIClient:
    return APIClient()


@pytest.fixture
def as_user():
    """as_user(user) → Bearer token bilan APIClient."""
    from apps.accounts.services import issue_tokens

    def factory(user) -> APIClient:
        access, _ = issue_tokens(user)
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
        return client

    return factory


@pytest.fixture
def owner_client(owner, as_user) -> APIClient:
    return as_user(owner)


@pytest.fixture
def seller_client(seller, as_user) -> APIClient:
    return as_user(seller)
