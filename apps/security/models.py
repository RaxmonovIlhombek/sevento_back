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
            val = (struct.unpack(">I", h[o:o + 4])[0] & 0x7FFFFFFF) % (10 ** digits)
            if f"{val:0{digits}d}" == code:
                return True
        return False
    except Exception:
        return False


class TwoFactorDevice(TimeStampedModel):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="totp_device")
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
