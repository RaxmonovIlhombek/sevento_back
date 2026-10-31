from rest_framework import serializers

from .models import Account, FiscalPeriod, FiscalYear, JournalEntry, JournalLine


class AccountSerializer(serializers.ModelSerializer):
    parent_code = serializers.CharField(source="parent.code", read_only=True)

    class Meta:
        model = Account
        fields = [
            "id",
            "code",
            "name",
            "account_type",
            "normal_balance",
            "parent",
            "parent_code",
            "is_active",
            "is_postable",
            "description",
            "created_at",
            "updated_at",
        ]


class FiscalYearSerializer(serializers.ModelSerializer):
    class Meta:
        model = FiscalYear
        fields = ["id", "year", "start_date", "end_date", "is_closed", "created_at", "updated_at"]


class FiscalPeriodSerializer(serializers.ModelSerializer):
    fiscal_year_value = serializers.IntegerField(source="fiscal_year.year", read_only=True)

    class Meta:
        model = FiscalPeriod
        fields = [
            "id",
            "fiscal_year",
            "fiscal_year_value",
            "number",
            "start_date",
            "end_date",
            "is_closed",
            "created_at",
            "updated_at",
        ]


class JournalLineSerializer(serializers.ModelSerializer):
    account_code = serializers.CharField(source="account.code", read_only=True)
    account_name = serializers.CharField(source="account.name", read_only=True)

    class Meta:
        model = JournalLine
        fields = ["id", "account", "account_code", "account_name", "description", "debit", "credit"]


class JournalEntrySerializer(serializers.ModelSerializer):
    lines = JournalLineSerializer(many=True)
    branch_name = serializers.CharField(source="branch.name", read_only=True)

    class Meta:
        model = JournalEntry
        fields = [
            "id",
            "number",
            "date",
            "fiscal_period",
            "branch",
            "branch_name",
            "description",
            "status",
            "posted_at",
            "posted_by",
            "reversed_by_entry",
            "created_by",
            "lines",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["number", "status", "posted_at", "posted_by", "reversed_by_entry", "created_by"]

    def create(self, validated_data):
        lines_data = validated_data.pop("lines", [])
        from django.contrib.auth import get_user_model

        user = self.context["request"].user
        from .services import create_entry

        entry = create_entry(
            user=user,
            date=validated_data["date"],
            fiscal_period=validated_data["fiscal_period"],
            branch=validated_data.get("branch"),
            description=validated_data.get("description", ""),
            lines=[
                {
                    "account": ld["account"],
                    "description": ld.get("description", ""),
                    "debit": ld.get("debit", 0),
                    "credit": ld.get("credit", 0),
                }
                for ld in lines_data
            ],
        )
        return entry

    def update(self, instance, validated_data):
        if instance.status != JournalEntry.Status.DRAFT:
            raise serializers.ValidationError("Faqat qoralama yozuvni tahrirlash mumkin")
        lines_data = validated_data.pop("lines", None)
        for attr, val in validated_data.items():
            setattr(instance, attr, val)
        instance.save()
        if lines_data is not None:
            instance.lines.all().delete()
            for ld in lines_data:
                JournalLine.objects.create(
                    entry=instance,
                    account=ld["account"],
                    description=ld.get("description", ""),
                    debit=ld.get("debit", 0),
                    credit=ld.get("credit", 0),
                )
        return instance
