"""2FA (TOTP) status/setup/verify/disable endpointlari uchun testlar."""

import pytest
from rest_framework import status

from apps.security.models import TwoFactorDevice, verify_totp
from apps.security.models import _generate_secret as generate_secret


def _valid_code(secret, step=30, digits=6):
    """models.verify_totp bilan bir xil algoritm bo'yicha joriy to'g'ri kodni hisoblaydi."""
    import base64
    import hashlib
    import hmac
    import struct
    import time

    key = base64.b32decode(secret + "=" * ((8 - len(secret) % 8) % 8))
    counter = int(time.time()) // step
    msg = struct.pack(">Q", counter)
    h = hmac.new(key, msg, hashlib.sha1).digest()
    o = h[-1] & 0x0F
    val = (struct.unpack(">I", h[o : o + 4])[0] & 0x7FFFFFFF) % (10**digits)
    return f"{val:0{digits}d}"


@pytest.mark.django_db
def test_status_disabled_when_no_device(seller_client):
    resp = seller_client.get("/api/v1/security/2fa/status/")
    assert resp.status_code == status.HTTP_200_OK
    assert resp.data == {"enabled": False}


@pytest.mark.django_db
def test_setup_creates_device(seller_client, seller):
    resp = seller_client.post("/api/v1/security/2fa/setup/")
    assert resp.status_code == status.HTTP_200_OK
    assert "secret" in resp.data
    assert "provisioning_uri" in resp.data
    assert TwoFactorDevice.objects.filter(user=seller).exists()


@pytest.mark.django_db
def test_setup_rotates_secret_if_not_verified(seller_client, seller):
    first = seller_client.post("/api/v1/security/2fa/setup/").data["secret"]
    second = seller_client.post("/api/v1/security/2fa/setup/").data["secret"]
    assert first != second


@pytest.mark.django_db
def test_setup_rejects_when_already_verified(seller_client, seller):
    dev = TwoFactorDevice.objects.create(user=seller, secret=generate_secret(), is_verified=True)
    resp = seller_client.post("/api/v1/security/2fa/setup/")
    assert resp.status_code == status.HTTP_400_BAD_REQUEST
    dev.refresh_from_db()
    assert dev.is_verified is True


@pytest.mark.django_db
def test_verify_without_setup_fails(seller_client):
    resp = seller_client.post("/api/v1/security/2fa/verify/", {"code": "000000"})
    assert resp.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_verify_with_wrong_code_fails(seller_client, seller):
    TwoFactorDevice.objects.create(user=seller, secret=generate_secret(), is_verified=False)
    resp = seller_client.post("/api/v1/security/2fa/verify/", {"code": "000000"})
    assert resp.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_verify_with_correct_code_enables_2fa(seller_client, seller):
    secret = generate_secret()
    dev = TwoFactorDevice.objects.create(user=seller, secret=secret, is_verified=False)
    code = _valid_code(secret)
    resp = seller_client.post("/api/v1/security/2fa/verify/", {"code": code})
    assert resp.status_code == status.HTTP_200_OK
    assert resp.data == {"enabled": True}
    dev.refresh_from_db()
    assert dev.is_verified is True
    assert dev.last_used_at is not None


@pytest.mark.django_db
def test_disable_without_device_returns_disabled(seller_client):
    resp = seller_client.post("/api/v1/security/2fa/disable/", {"code": "000000"})
    assert resp.status_code == status.HTTP_200_OK
    assert resp.data == {"enabled": False}


@pytest.mark.django_db
def test_disable_unverified_device_deletes_without_code(seller_client, seller):
    TwoFactorDevice.objects.create(user=seller, secret=generate_secret(), is_verified=False)
    resp = seller_client.post("/api/v1/security/2fa/disable/", {})
    assert resp.status_code == status.HTTP_200_OK
    assert resp.data == {"enabled": False}
    assert not TwoFactorDevice.objects.filter(user=seller).exists()


@pytest.mark.django_db
def test_disable_verified_device_requires_correct_code(seller_client, seller):
    secret = generate_secret()
    TwoFactorDevice.objects.create(user=seller, secret=secret, is_verified=True)
    bad = seller_client.post("/api/v1/security/2fa/disable/", {"code": "000000"})
    assert bad.status_code == status.HTTP_400_BAD_REQUEST
    assert TwoFactorDevice.objects.filter(user=seller).exists()

    good_code = _valid_code(secret)
    ok = seller_client.post("/api/v1/security/2fa/disable/", {"code": good_code})
    assert ok.status_code == status.HTTP_200_OK
    assert not TwoFactorDevice.objects.filter(user=seller).exists()


def test_verify_totp_rejects_malformed_code():
    assert verify_totp("JBSWY3DPEHPK3PXP", "not-a-code") is False
    assert verify_totp("JBSWY3DPEHPK3PXP", "123") is False
