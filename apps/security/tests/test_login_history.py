import pytest
from django.db import transaction

from apps.security.devices import parse_user_agent
from apps.security.models import LoginEvent

pytestmark = pytest.mark.django_db

CHROME_WIN = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)
IPHONE = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1"
)


def test_parse_user_agent():
    assert parse_user_agent(CHROME_WIN) == {
        "browser": "Chrome 126",
        "os": "Windows",
        "device_type": "desktop",
    }
    assert parse_user_agent(IPHONE) == {
        "browser": "Safari 17",
        "os": "iOS",
        "device_type": "mobile",
    }
    assert parse_user_agent("")["device_type"] == ""


def _login(client, username, password, ua=CHROME_WIN, ip="10.1.2.3"):
    return client.post(
        "/api/v1/auth/login/",
        {"username": username, "password": password},
        format="json",
        HTTP_USER_AGENT=ua,
        HTTP_X_FORWARDED_FOR=ip,
    )


def test_login_and_failure_are_recorded(owner, api_client, django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks(execute=True):
        assert _login(api_client, "rahbar", "parol12345").status_code == 200
        assert _login(api_client, "rahbar", "xato", ua=IPHONE, ip="10.9.9.9").status_code == 401

    ok, bad = LoginEvent.objects.order_by("id")
    assert (ok.success, ok.user_id, ok.ip, ok.browser, ok.device_type) == (
        True,
        owner.pk,
        "10.1.2.3",
        "Chrome 126",
        "desktop",
    )
    assert (bad.success, bad.user_id, bad.reason, bad.os, bad.device_type) == (
        False,
        None,
        "bad_credentials",
        "iOS",
        "mobile",
    )


def test_list_summary_require_capability(
    owner_client, seller_client, owner, django_capture_on_commit_callbacks
):
    with django_capture_on_commit_callbacks(execute=True):
        with transaction.atomic():
            LoginEvent.objects.create(
                user=owner, username="rahbar", ip="1.1.1.1", created_at=owner.date_joined
            )
    assert seller_client.get("/api/v1/security/logins/").status_code == 403
    assert seller_client.get("/api/v1/security/logins/summary/").status_code == 403
    assert owner_client.get("/api/v1/security/logins/").status_code == 200
    data = owner_client.get("/api/v1/security/logins/summary/").json()
    row = next(r for r in data if r["username"] == "rahbar")
    assert row["last_ip"] == "1.1.1.1"
    assert row["logins_30d"] >= 0


def test_mine_is_available_to_everyone(seller_client, seller):
    LoginEvent.objects.create(user=seller, username=seller.username, created_at=seller.date_joined)
    LoginEvent.objects.create(username="boshqa", created_at=seller.date_joined)
    response = seller_client.get("/api/v1/security/logins/mine/")
    assert response.status_code == 200
    assert [r["username"] for r in response.json()] == [seller.username]
