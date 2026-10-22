import pytest

from apps.audit.models import AuditLog

pytestmark = pytest.mark.django_db

LOGIN = "/api/v1/auth/login/"
REFRESH = "/api/v1/auth/refresh/"
LOGOUT = "/api/v1/auth/logout/"
ME = "/api/v1/auth/me/"
COOKIE = "sevento_refresh"
ORIGIN = {"HTTP_ORIGIN": "http://localhost:5173"}


def _login(client, username="sotuvchi", password="parol12345"):
    return client.post(LOGIN, {"username": username, "password": password})


def test_login_returns_access_and_sets_refresh_cookie(
    api_client, seller, branch, django_capture_on_commit_callbacks
):
    with django_capture_on_commit_callbacks(execute=True):
        response = _login(api_client)

    assert response.status_code == 200
    body = response.json()
    assert body["access"]
    user = body["user"]
    assert user["username"] == "sotuvchi"
    assert user["role"] == {"code": "seller", "name": "Sotuvchi"}
    assert user["all_branches"] is False
    assert [b["id"] for b in user["branches"]] == [branch.id]
    assert user["branches"][0]["is_default"] is True
    assert "sales.create" in user["capabilities"]
    assert "users.manage" not in user["capabilities"]
    assert "refresh" not in body  # refresh faqat cookie da

    cookie = response.cookies[COOKIE]
    assert cookie.value
    assert cookie["httponly"] is True
    assert cookie["samesite"] == "Strict"
    assert cookie["path"] == "/api/v1/auth/"
    assert int(cookie["max-age"]) == 7 * 24 * 3600

    seller.refresh_from_db()
    assert seller.last_login is not None
    assert AuditLog.objects.filter(event_name="user.logged_in", actor=seller).exists()


def test_login_wrong_password(api_client, seller, django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks(execute=True):
        response = _login(api_client, password="notogri")
    assert response.status_code == 401
    error = response.json()["error"]
    assert error["code"] == "authentication_failed"
    assert error["message"] == "Login yoki parol noto'g'ri"
    assert COOKIE not in response.cookies
    log = AuditLog.objects.get(event_name="user.login_failed")
    assert log.payload == {"username": "sotuvchi", "reason": "bad_credentials"}
    assert log.actor is None


def test_login_inactive_user(api_client, seller, django_capture_on_commit_callbacks):
    seller.is_active = False
    seller.save()
    with django_capture_on_commit_callbacks(execute=True):
        response = _login(api_client)
    assert response.status_code == 401
    assert AuditLog.objects.get(event_name="user.login_failed").payload["reason"] == "inactive"


def test_login_validation(api_client):
    response = api_client.post(LOGIN, {"username": "x"})
    assert response.status_code == 400
    error = response.json()["error"]
    assert error["code"] == "validation_error"
    assert [(d["field"], d["code"]) for d in error["details"]] == [("password", "required")]


def test_access_token_grants_me(api_client, seller):
    access = _login(api_client).json()["access"]
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
    response = api_client.get(ME)
    assert response.status_code == 200
    assert response.json()["username"] == "sotuvchi"


def test_me_for_owner_lists_all_active_branches(owner_client, branch, branch2):
    branch2.is_active = False
    branch2.save()
    body = owner_client.get(ME).json()
    assert body["all_branches"] is True
    assert [b["id"] for b in body["branches"]] == [branch.id]
    assert "users.manage" in body["capabilities"]


def test_me_requires_auth(api_client):
    assert api_client.get(ME).status_code == 401


def test_refresh_rotates_and_blacklists_old_token(api_client, seller):
    _login(api_client)
    old_refresh = api_client.cookies[COOKIE].value

    response = api_client.post(REFRESH, **ORIGIN)
    assert response.status_code == 200
    assert response.json()["access"]
    new_refresh = response.cookies[COOKIE].value
    assert new_refresh and new_refresh != old_refresh

    # eski refresh endi qora ro'yxatda
    api_client.cookies[COOKIE] = old_refresh
    response = api_client.post(REFRESH, **ORIGIN)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "token_not_valid"

    # yangisi hali ishlaydi
    api_client.cookies[COOKIE] = new_refresh
    assert api_client.post(REFRESH, **ORIGIN).status_code == 200


def test_refresh_without_cookie(api_client):
    response = api_client.post(REFRESH, **ORIGIN)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "token_not_valid"


def test_refresh_with_foreign_origin_rejected(api_client, seller):
    _login(api_client)
    response = api_client.post(REFRESH, HTTP_ORIGIN="https://evil.example")
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "origin_not_allowed"


def test_refresh_with_referer_only(api_client, seller):
    _login(api_client)
    assert api_client.post(REFRESH, HTTP_REFERER="http://localhost:5173/sales").status_code == 200
    assert api_client.post(REFRESH, HTTP_REFERER="https://evil.example/").status_code == 403


def test_refresh_for_deactivated_user(api_client, seller):
    _login(api_client)
    seller.is_active = False
    seller.save()
    response = api_client.post(REFRESH, **ORIGIN)
    assert response.status_code == 401


def test_logout_blacklists_and_clears_cookie(api_client, seller):
    _login(api_client)
    refresh = api_client.cookies[COOKIE].value

    response = api_client.post(LOGOUT, **ORIGIN)
    assert response.status_code == 204
    assert response.cookies[COOKIE].value == ""
    assert response.cookies[COOKIE]["max-age"] == 0

    api_client.cookies[COOKIE] = refresh
    assert api_client.post(REFRESH, **ORIGIN).status_code == 401


def test_logout_without_cookie_is_ok(api_client):
    assert api_client.post(LOGOUT).status_code == 204


def test_change_password(owner_client, owner, api_client, django_capture_on_commit_callbacks):
    url = "/api/v1/auth/change-password/"
    response = owner_client.post(url, {"current_password": "xato", "new_password": "yangiParol99"})
    assert response.status_code == 400
    assert response.json()["error"]["details"][0]["field"] == "current_password"

    response = owner_client.post(url, {"current_password": "parol12345", "new_password": "123"})
    assert response.status_code == 400
    assert response.json()["error"]["details"][0]["code"] == "password_too_weak"

    with django_capture_on_commit_callbacks(execute=True):
        response = owner_client.post(
            url, {"current_password": "parol12345", "new_password": "yangiParol99"}
        )
    assert response.status_code == 204
    assert _login(api_client, "rahbar", "yangiParol99").status_code == 200
    log = AuditLog.objects.get(event_name="user.password_changed")
    assert log.payload == {"user_id": owner.id, "by_self": True}


def test_capabilities_list(seller_client):
    response = seller_client.get("/api/v1/auth/capabilities/")
    assert response.status_code == 200
    codes = {c["code"] for c in response.json()}
    assert {"sales.create", "users.manage", "audit.view"} <= codes
