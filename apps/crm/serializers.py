from rest_framework import serializers

from .models import Activity, Deal, Lead


class LeadSerializer(serializers.ModelSerializer):
    class Meta:
        model = Lead
        fields = [
            "id",
            "name",
            "company",
            "phone",
            "email",
            "source",
            "status",
            "owner",
            "branch",
            "notes",
            "created_at",
            "updated_at",
        ]


class DealSerializer(serializers.ModelSerializer):
    class Meta:
        model = Deal
        fields = [
            "id",
            "name",
            "lead",
            "customer",
            "owner",
            "branch",
            "stage",
            "amount",
            "currency",
            "expected_close_date",
            "notes",
            "created_at",
            "updated_at",
        ]


class ActivitySerializer(serializers.ModelSerializer):
    class Meta:
        model = Activity
        fields = [
            "id",
            "activity_type",
            "subject",
            "description",
            "due_date",
            "completed",
            "lead",
            "deal",
            "owner",
            "created_at",
            "updated_at",
        ]
