from django.utils import timezone
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.filters import OrderingFilter
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import Notification
from .serializers import NotificationSerializer


class NotificationViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = NotificationSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [OrderingFilter]
    ordering = ["-created_at"]
    lookup_value_regex = r"\d+"

    def get_queryset(self):
        return Notification.objects.filter(user=self.request.user)

    @action(detail=True, methods=["post"])
    def read(self, request, pk=None):
        n = self.get_object()
        if not n.is_read:
            n.is_read = True
            n.read_at = timezone.now()
            n.save(update_fields=["is_read", "read_at", "updated_at"])
        return Response(self.get_serializer(n).data)

    @action(detail=False, methods=["post"])
    def read_all(self, request):
        qs = self.get_queryset().filter(is_read=False)
        qs.update(is_read=True, read_at=timezone.now())
        return Response({"updated": qs.count()})
