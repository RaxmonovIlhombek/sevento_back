from rest_framework import serializers

from apps.sales.models import Sale

from .models import Fulfillment, FulfillmentStep


class StepSerializer(serializers.ModelSerializer):
    actor_name = serializers.CharField(source="actor.full_name", read_only=True, default=None)
    status_label = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = FulfillmentStep
        fields = ["id", "status", "status_label", "actor", "actor_name", "note", "at"]
        read_only_fields = fields


class ItemSerializer(serializers.Serializer):
    product_name = serializers.CharField(source="product.name")
    quantity = serializers.DecimalField(max_digits=14, decimal_places=3)
    unit = serializers.CharField(source="product.unit.name", default="")


class FulfillmentSerializer(serializers.ModelSerializer):
    number = serializers.CharField(source="sale.number", read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    branch_name = serializers.CharField(source="branch.name", read_only=True)
    customer_name = serializers.CharField(source="sale.customer.name", read_only=True, default=None)
    total = serializers.DecimalField(
        source="sale.total", max_digits=20, decimal_places=4, read_only=True
    )
    currency_code = serializers.CharField(source="sale.currency.code", read_only=True)
    packed_by_name = serializers.CharField(
        source="packed_by.full_name", read_only=True, default=None
    )
    verified_by_name = serializers.CharField(
        source="verified_by.full_name", read_only=True, default=None
    )
    courier_name = serializers.CharField(source="courier.full_name", read_only=True, default=None)

    class Meta:
        model = Fulfillment
        fields = [
            "id",
            "sale",
            "number",
            "branch",
            "branch_name",
            "status",
            "status_label",
            "address",
            "contact_phone",
            "note",
            "reject_reason",
            "customer_name",
            "total",
            "currency_code",
            "packed_by",
            "packed_by_name",
            "packed_at",
            "verified_by",
            "verified_by_name",
            "verified_at",
            "courier",
            "courier_name",
            "accepted_at",
            "delivered_at",
            "delivered_note",
            "cancelled_at",
            "cancel_reason",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class FulfillmentDetailSerializer(FulfillmentSerializer):
    items = ItemSerializer(source="sale.items", many=True, read_only=True)
    steps = StepSerializer(many=True, read_only=True)

    class Meta(FulfillmentSerializer.Meta):
        fields = [*FulfillmentSerializer.Meta.fields, "items", "steps"]
        read_only_fields = fields


class FulfillmentCreateSerializer(serializers.Serializer):
    sale = serializers.PrimaryKeyRelatedField(queryset=Sale.objects.select_related("customer"))
    address = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")
    contact_phone = serializers.CharField(
        max_length=30, required=False, allow_blank=True, default=""
    )
    note = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")


class NoteSerializer(serializers.Serializer):
    note = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")


class ReasonSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=255)


class SummarySerializer(serializers.Serializer):
    pending = serializers.IntegerField()
    packed = serializers.IntegerField()
    ready = serializers.IntegerField()
    on_the_way = serializers.IntegerField()
    delivered = serializers.IntegerField()
    cancelled = serializers.IntegerField()
