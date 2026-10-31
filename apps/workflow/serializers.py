from rest_framework import serializers

from .models import ApprovalInstance, ApprovalRule, ApprovalStep


class ApprovalRuleSerializer(serializers.ModelSerializer):
    approver_name = serializers.CharField(source="approver.full_name", read_only=True)

    class Meta:
        model = ApprovalRule
        fields = [
            "id",
            "entity_type",
            "min_amount",
            "max_amount",
            "branch",
            "approver",
            "approver_name",
            "sequence",
            "is_active",
            "created_at",
            "updated_at",
        ]


class ApprovalStepSerializer(serializers.ModelSerializer):
    approver_name = serializers.CharField(source="approver.full_name", read_only=True)

    class Meta:
        model = ApprovalStep
        fields = ["id", "approver", "approver_name", "sequence", "decision", "decided_at", "comment", "created_at"]


class ApprovalInstanceSerializer(serializers.ModelSerializer):
    steps = ApprovalStepSerializer(many=True, read_only=True)
    requested_by_name = serializers.CharField(source="requested_by.full_name", read_only=True)

    class Meta:
        model = ApprovalInstance
        fields = [
            "id",
            "entity_type",
            "entity_id",
            "status",
            "requested_by",
            "requested_by_name",
            "branch",
            "amount",
            "decided_at",
            "notes",
            "steps",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["status", "decided_at"]
