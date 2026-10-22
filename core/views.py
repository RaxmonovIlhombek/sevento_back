from django.core.cache import cache
from django.db import connection
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from . import settings_registry, settings_service
from .api.permissions import capability_required
from .serializers import HealthSerializer, SystemSettingSerializer, SystemSettingUpdateSerializer


class HealthView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    @extend_schema(responses=HealthSerializer, tags=["system"])
    def get(self, request):
        db_ok = redis_ok = True
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
        except Exception:  # noqa: BLE001
            db_ok = False
        try:
            cache.set("health", 1, 5)
            redis_ok = cache.get("health") == 1
        except Exception:  # noqa: BLE001
            redis_ok = False
        ok = db_ok and redis_ok
        return Response(
            {"status": "ok" if ok else "degraded", "db": db_ok, "redis": redis_ok},
            status=status.HTTP_200_OK if ok else status.HTTP_503_SERVICE_UNAVAILABLE,
        )


class SettingListView(APIView):
    permission_classes = [IsAuthenticated, capability_required("settings.manage")]

    @extend_schema(responses=SystemSettingSerializer(many=True), tags=["settings"])
    def get(self, request):
        return Response(SystemSettingSerializer(settings_service.get_all(), many=True).data)


class SettingDetailView(APIView):
    permission_classes = [IsAuthenticated, capability_required("settings.manage")]

    def _get_def(self, key):
        try:
            return settings_registry.get_def(key)
        except KeyError:
            raise NotFound() from None

    @extend_schema(responses=SystemSettingSerializer, tags=["settings"])
    def get(self, request, key):
        self._get_def(key)
        item = next(i for i in settings_service.get_all() if i["key"] == key)
        return Response(SystemSettingSerializer(item).data)

    @extend_schema(
        request=SystemSettingUpdateSerializer, responses=SystemSettingSerializer, tags=["settings"]
    )
    def put(self, request, key):
        self._get_def(key)
        serializer = SystemSettingUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            item = settings_service.set(
                key=key, value=serializer.validated_data["value"], actor=request.user
            )
        except ValueError as exc:
            raise ValidationError({"value": [str(exc)]}) from None
        return Response(SystemSettingSerializer(item).data)

    @extend_schema(responses=SystemSettingSerializer, tags=["settings"])
    def delete(self, request, key):
        """Qiymatni default ga qaytaradi."""
        self._get_def(key)
        item = settings_service.reset(key=key, actor=request.user)
        return Response(SystemSettingSerializer(item).data)
