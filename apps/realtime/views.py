from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from core.api.permissions import capability_required

from . import services
from .serializers import NoticeSerializer, TicketSerializer


class TicketView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "ws_ticket"

    @extend_schema(
        request=None,
        responses={201: TicketSerializer},
        tags=["realtime"],
        summary="WebSocket uchun bir martalik ticket (30 s)",
    )
    def post(self, request):
        data = services.issue_ticket(user=request.user)
        return Response(TicketSerializer(data).data, status=status.HTTP_201_CREATED)


class NoticeView(APIView):
    permission_classes = [IsAuthenticated, capability_required("settings.manage")]

    @extend_schema(
        request=NoticeSerializer,
        responses={204: None},
        tags=["realtime"],
        summary="Barcha ulangan foydalanuvchilarga xabar",
    )
    def post(self, request):
        serializer = NoticeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.send_notice(actor=request.user, **serializer.validated_data)
        return Response(status=status.HTTP_204_NO_CONTENT)
