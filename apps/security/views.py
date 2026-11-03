from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db.models import Count, OuterRef, Subquery
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.api.mixins import CapabilityViewSetMixin

from .filters import LoginEventFilter
from .models import LoginEvent, TwoFactorDevice, _generate_secret, verify_totp
from .serializers import (
    LoginEventSerializer,
    TwoFactorCodeSerializer,
    TwoFactorSetupSerializer,
    TwoFactorStatusSerializer,
    UserLoginSummarySerializer,
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


@extend_schema(tags=["security"])
class LoginEventViewSet(CapabilityViewSetMixin, viewsets.ReadOnlyModelViewSet):
    """Kirish tarixi. Ro'yxat va xulosa — `users.manage`; `mine` — har kim o'zinikini ko'radi."""

    queryset = LoginEvent.objects.none()
    serializer_class = LoginEventSerializer
    capability_map = {
        "list": "users.manage",
        "retrieve": "users.manage",
        "summary": "users.manage",
        "mine": None,
    }
    filterset_class = LoginEventFilter
    search_fields = ["username", "user__full_name", "ip"]
    ordering_fields = ["created_at", "id"]
    ordering = ["-created_at", "-id"]

    def get_queryset(self):
        return LoginEvent.objects.select_related("user", "user__role")

    @extend_schema(responses=LoginEventSerializer(many=True))
    @action(detail=False, methods=["get"])
    def mine(self, request):
        """Joriy foydalanuvchining o'z kirishlari (so'nggi 50 ta)."""
        rows = self.get_queryset().filter(user=request.user)[:50]
        return Response(LoginEventSerializer(rows, many=True).data)

    @extend_schema(responses=UserLoginSummarySerializer(many=True))
    @action(detail=False, methods=["get"], pagination_class=None)
    def summary(self, request):
        """Har bir foydalanuvchi: oxirgi kirish, qurilma, IP va oxirgi 30 kundagi kirishlar soni."""
        since = timezone.now() - timedelta(days=30)
        last_ok = LoginEvent.objects.filter(user=OuterRef("pk"), success=True).order_by(
            "-created_at", "-id"
        )
        users = (
            get_user_model()
            .objects.select_related("role")
            .annotate(
                last_ip=Subquery(last_ok.values("ip")[:1]),
                last_browser=Subquery(last_ok.values("browser")[:1]),
                last_os=Subquery(last_ok.values("os")[:1]),
                last_device_type=Subquery(last_ok.values("device_type")[:1]),
            )
            .order_by("-last_login", "full_name")
        )
        failed = dict(
            LoginEvent.objects.filter(success=False, created_at__gte=since)
            .exclude(username="")
            .values_list("username")
            .annotate(n=Count("id"))
        )
        logins = dict(
            LoginEvent.objects.filter(success=True, created_at__gte=since, user__isnull=False)
            .values_list("user_id")
            .annotate(n=Count("id"))
        )
        rows = [
            {
                "id": u.pk,
                "username": u.username,
                "full_name": u.full_name,
                "role_name": u.role.name if u.role_id else None,
                "is_active": u.is_active,
                "last_login": u.last_login,
                "last_ip": u.last_ip or "",
                "last_browser": u.last_browser or "",
                "last_os": u.last_os or "",
                "last_device_type": u.last_device_type or "",
                "logins_30d": logins.get(u.pk, 0),
                "failed_30d": failed.get(u.username, 0),
            }
            for u in users
        ]
        return Response(UserLoginSummarySerializer(rows, many=True).data)
