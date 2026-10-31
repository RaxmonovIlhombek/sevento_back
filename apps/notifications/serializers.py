from rest_framework import serializers

from .models import Notification


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = [
            "id",
            "title",
            "message",
            "notification_type",
            "is_read",
            "read_at",
            "link",
            "source",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "title", "message", "notification_type", "link", "source", "created_at", "updated_at", "read_at"]
