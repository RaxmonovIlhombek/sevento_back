from rest_framework import serializers


class TicketSerializer(serializers.Serializer):
    ticket = serializers.CharField()
    expires_in = serializers.IntegerField()


class NoticeSerializer(serializers.Serializer):
    level = serializers.ChoiceField(choices=["info", "warning", "error"], default="info")
    message = serializers.CharField(max_length=500)
