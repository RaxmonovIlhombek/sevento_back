from decimal import Decimal

from rest_framework import serializers

from .models import ApprovalInstance, ApprovalRule, ApprovalStep
from .services import current_step
from .types import REQUEST_TYPES


class ApprovalRuleSerializer(serializers.ModelSerializer):
    approver_name = serializers.CharField(source="approver.full_name", read_only=True)
    branch_name = serializers.CharField(source="branch.name", read_only=True, default=None)
    type_label = serializers.SerializerMethodField()

    class Meta:
        model = ApprovalRule
        fields = [
            "id",
            "entity_type",
            "type_label",
            "min_amount",
            "max_amount",
            "branch",
            "branch_name",
            "approver",
            "approver_name",
            "sequence",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at"]

    def get_type_label(self, obj) -> str:
        return REQUEST_TYPES.get(obj.entity_type, obj.entity_type)

    def validate_entity_type(self, value):
        if value not in REQUEST_TYPES:
            raise serializers.ValidationError("Noma'lum so'rov turi")
        return value

    def validate(self, attrs):
        lo = attrs.get("min_amount", getattr(self.instance, "min_amount", Decimal(0)))
        hi = attrs.get("max_amount", getattr(self.instance, "max_amount", None))
        if hi is not None and hi < lo:
            raise serializers.ValidationError(
                {"max_amount": "Eng ko'p summa eng kam summadan kichik bo'lmasligi kerak"}
            )
        return attrs


class ApprovalStepSerializer(serializers.ModelSerializer):
    approver_name = serializers.CharField(source="approver.full_name", read_only=True)

    class Meta:
        model = ApprovalStep
        fields = [
            "id",
            "approver",
            "approver_name",
            "sequence",
            "decision",
            "decided_at",
            "comment",
            "created_at",
        ]


class ApprovalInstanceSerializer(serializers.ModelSerializer):
    steps = ApprovalStepSerializer(many=True, read_only=True)
    requested_by_name = serializers.CharField(source="requested_by.full_name", read_only=True)
    branch_name = serializers.CharField(source="branch.name", read_only=True, default=None)
    type_label = serializers.SerializerMethodField()
    current_approver_name = serializers.SerializerMethodField()
    can_decide = serializers.SerializerMethodField()
    can_cancel = serializers.SerializerMethodField()

    class Meta:
        model = ApprovalInstance
        fields = [
            "id",
            "entity_type",
            "type_label",
            "entity_id",
            "title",
            "status",
            "requested_by",
            "requested_by_name",
            "branch",
            "branch_name",
            "amount",
            "decided_at",
            "notes",
            "steps",
            "current_approver_name",
            "can_decide",
            "can_cancel",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    def get_type_label(self, obj) -> str:
        return REQUEST_TYPES.get(obj.entity_type, obj.entity_type)

    def _current(self, obj):
        if obj.status != ApprovalInstance.Status.PENDING:
            return None
        return current_step(obj)

    def get_current_approver_name(self, obj) -> str | None:
        step = self._current(obj)
        return step.approver.full_name if step else None

    def get_can_decide(self, obj) -> bool:
        step = self._current(obj)
        return bool(step and step.approver_id == self.context["request"].user.id)

    def get_can_cancel(self, obj) -> bool:
        user = self.context["request"].user
        return obj.status == ApprovalInstance.Status.PENDING and (
            obj.requested_by_id == user.id or user.has_capability("workflow.manage")
        )


class CreateRequestSerializer(serializers.Serializer):
    entity_type = serializers.ChoiceField(choices=list(REQUEST_TYPES))
    title = serializers.CharField(max_length=200)
    amount = serializers.DecimalField(max_digits=20, decimal_places=4, min_value=0)
    branch = serializers.IntegerField(required=False, allow_null=True)
    notes = serializers.CharField(required=False, allow_blank=True, max_length=2000, default="")


class DecisionSerializer(serializers.Serializer):
    comment = serializers.CharField(required=False, allow_blank=True, max_length=1000, default="")


class WorkflowSummarySerializer(serializers.Serializer):
    assigned = serializers.IntegerField()
    mine_pending = serializers.IntegerField()
