"""OpenAPI hujjat uchun umumiy xato javobi komponenti."""

from drf_spectacular.utils import OpenApiResponse
from rest_framework import serializers


class ErrorDetailSerializer(serializers.Serializer):
    field = serializers.CharField(allow_null=True)
    code = serializers.CharField()
    message = serializers.CharField()


class ErrorBodySerializer(serializers.Serializer):
    code = serializers.CharField()
    message = serializers.CharField()
    details = ErrorDetailSerializer(many=True)
    request_id = serializers.CharField()


class ErrorResponseSerializer(serializers.Serializer):
    error = ErrorBodySerializer()


ERROR_RESPONSE = OpenApiResponse(response=ErrorResponseSerializer, description="Xato")
