from rest_framework import serializers


class TwoFactorStatusSerializer(serializers.Serializer):
    enabled = serializers.BooleanField()


class TwoFactorSetupSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    is_verified = serializers.BooleanField()
    secret = serializers.CharField()
    provisioning_uri = serializers.CharField()


class TwoFactorCodeSerializer(serializers.Serializer):
    code = serializers.CharField()
