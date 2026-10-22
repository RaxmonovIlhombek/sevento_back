from rest_framework import serializers


class SystemSettingSerializer(serializers.Serializer):
    key = serializers.CharField(read_only=True)
    type = serializers.CharField(read_only=True)
    choices = serializers.ListField(child=serializers.CharField(), read_only=True)
    description = serializers.CharField(read_only=True)
    default = serializers.JSONField(read_only=True)
    value = serializers.JSONField()
    is_overridden = serializers.BooleanField(read_only=True)
    updated_at = serializers.DateTimeField(read_only=True, allow_null=True)
    updated_by = serializers.CharField(read_only=True, allow_null=True)


class SystemSettingUpdateSerializer(serializers.Serializer):
    value = serializers.JSONField()


class HealthSerializer(serializers.Serializer):
    status = serializers.CharField()
    db = serializers.BooleanField()
    redis = serializers.BooleanField()
