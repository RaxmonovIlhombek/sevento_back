from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import TwoFactorDevice, _generate_secret, verify_totp
from .serializers import (
    TwoFactorCodeSerializer,
    TwoFactorSetupSerializer,
    TwoFactorStatusSerializer,
)


class SecurityViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = TwoFactorStatusSerializer

    @extend_schema(responses=TwoFactorStatusSerializer)
    @action(detail=False, methods=["get"])
    def status(self, request):
        try:
            dev = request.user.totp_device
            return Response({"enabled": dev.is_verified})
        except TwoFactorDevice.DoesNotExist:
            return Response({"enabled": False})

    @extend_schema(responses=TwoFactorSetupSerializer)
    @action(detail=False, methods=["post"])
    def setup(self, request):
        dev, created = TwoFactorDevice.objects.get_or_create(
            user=request.user, defaults={"secret": _generate_secret(), "is_verified": False}
        )
        if not created and dev.is_verified:
            return Response({"detail": "2FA allaqachon yoqilgan"}, status=400)
        if not created:
            dev.secret = _generate_secret()
            dev.is_verified = False
            dev.save(update_fields=["secret", "is_verified", "updated_at"])
        return Response(
            {
                "id": dev.id,
                "is_verified": dev.is_verified,
                "secret": dev.secret,
                "provisioning_uri": dev.provisioning_uri(),
            }
        )

    @extend_schema(request=TwoFactorCodeSerializer, responses=TwoFactorStatusSerializer)
    @action(detail=False, methods=["post"])
    def verify(self, request):
        code = request.data.get("code")
        try:
            dev = request.user.totp_device
        except TwoFactorDevice.DoesNotExist:
            return Response({"detail": "Avval setup qiling"}, status=400)
        if verify_totp(dev.secret, code):
            dev.is_verified = True
            dev.last_used_at = timezone.now()
            dev.save(update_fields=["is_verified", "last_used_at", "updated_at"])
            return Response({"enabled": True})
        return Response({"detail": "Noto'g'ri kod"}, status=400)

    @extend_schema(request=TwoFactorCodeSerializer, responses=TwoFactorStatusSerializer)
    @action(detail=False, methods=["post"])
    def disable(self, request):
        code = request.data.get("code")
        try:
            dev = request.user.totp_device
        except TwoFactorDevice.DoesNotExist:
            return Response({"enabled": False})
        if not dev.is_verified:
            dev.delete()
            return Response({"enabled": False})
        if verify_totp(dev.secret, code):
            dev.delete()
            return Response({"enabled": False})
        return Response({"detail": "Noto'g'ri kod"}, status=400)

