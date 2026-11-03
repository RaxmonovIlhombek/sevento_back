import base64
import hashlib
import hmac
import os
import struct
import time

from django.conf import settings
from django.db import models

from core.models import TimeStampedModel


def _generate_secret():
    return base64.b32encode(os.urandom(20)).decode("ascii").rstrip("=")


def verify_totp(secret, code, window=1, step=30, digits=6):
    try:
        code = str(code).strip()
        if not code.isdigit() or len(code) != digits:
            return False
        key = base64.b32decode(secret + "=" * ((8 - len(secret) % 8) % 8))
        now = int(time.time()) // step
        for offset in range(-window, window + 1):
            counter = now + offset
            msg = struct.pack(">Q", counter)
            h = hmac.new(key, msg, hashlib.sha1).digest()
            o = h[-1] & 0x0F
            val = (struct.unpack(">I", h[o : o + 4])[0] & 0x7FFFFFFF) % (10**digits)
            if f"{val:0{digits}d}" == code:
                return True
        return False
    except Exception:
        return False


class TwoFactorDevice(TimeStampedModel):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="totp_device"
    )
    secret = models.CharField(max_length=64)
    is_verified = models.BooleanField(default=False)
    last_used_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"2FA for {self.user_id} (verified={self.is_verified})"

    def provisioning_uri(self, issuer="Sevento"):
        return (
            f"otpauth://totp/{issuer}:{self.user.username}?secret={self.secret}"
            f"&issuer={issuer}&algorithm=SHA1&digits=6&period=30"
        )


class LoginEvent(models.Model):
    """Kirish urinishlari (muvaffaqiyatli va xato): kim, qachon, qaysi qurilma va IP dan."""

    class Reason(models.TextChoices):
        BAD_CREDENTIALS = "bad_credentials", "Login yoki parol xato"
        INACTIVE = "inactive", "Hisob o'chirilgan"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    username = models.CharField(max_length=150, db_index=True)
    success = models.BooleanField(default=True, db_index=True)
    reason = models.CharField(max_length=20, blank=True)
    ip = models.CharField(max_length=45, blank=True)
    user_agent = models.CharField(max_length=500, blank=True)
    browser = models.CharField(max_length=60, blank=True)
    os = models.CharField(max_length=60, blank=True)
    device_type = models.CharField(max_length=20, blank=True)  # desktop | mobile | tablet | bot
    created_at = models.DateTimeField(db_index=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [models.Index(fields=["user", "-created_at"])]

    def __str__(self):
        return f"{self.username} {'✓' if self.success else '✗'} {self.created_at:%Y-%m-%d %H:%M}"
