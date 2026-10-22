from rest_framework import serializers

from .models import AuditLog


class AuditLogSerializer(serializers.ModelSerializer):
    actor_username = serializers.CharField(source="actor.username", read_only=True, default=None)
    actor_full_name = serializers.CharField(source="actor.full_name", read_only=True, default=None)
    branch_name = serializers.CharField(source="branch.name", read_only=True, default=None)

    class Meta:
        model = AuditLog
        fields = [
            "id",
            "event_name",
            "aggregate_type",
            "aggregate_id",
            "actor",
            "actor_username",
            "actor_full_name",
            "branch",
            "branch_name",
            "payload",
            "ip",
            "request_id",
            "created_at",
        ]
        read_only_fields = fields
