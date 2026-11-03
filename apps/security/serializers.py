from rest_framework import serializers

from .models import LoginEvent


class TwoFactorStatusSerializer(serializers.Serializer):
    enabled = serializers.BooleanField()


class TwoFactorSetupSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    is_verified = serializers.BooleanField()
    secret = serializers.CharField()
    provisioning_uri = serializers.CharField()


class TwoFactorCodeSerializer(serializers.Serializer):
    code = serializers.CharField()


class LoginEventSerializer(serializers.ModelSerializer):
    user_full_name = serializers.CharField(source="user.full_name", read_only=True, default=None)
    role_name = serializers.CharField(source="user.role.name", read_only=True, default=None)

    class Meta:
        model = LoginEvent
        fields = [
            "id",
            "user",
            "username",
            "user_full_name",
            "role_name",
            "success",
            "reason",
            "ip",
            "browser",
            "os",
            "device_type",
            "created_at",
        ]
        read_only_fields = fields


class UserLoginSummarySerializer(serializers.Serializer):
    """Har bir foydalanuvchining oxirgi kirishi — 'kim qachon va qaysi qurilmadan kirgan'."""

    id = serializers.IntegerField()
    username = serializers.CharField()
    full_name = serializers.CharField()
    role_name = serializers.CharField(allow_null=True)
    is_active = serializers.BooleanField()
    last_login = serializers.DateTimeField(allow_null=True)
    last_ip = serializers.CharField(allow_blank=True)
    last_browser = serializers.CharField(allow_blank=True)
    last_os = serializers.CharField(allow_blank=True)
    last_device_type = serializers.CharField(allow_blank=True)
    logins_30d = serializers.IntegerField()
    failed_30d = serializers.IntegerField()
