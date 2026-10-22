from rest_framework import serializers

from .models import Branch


class BranchSerializer(serializers.ModelSerializer):
    class Meta:
        model = Branch
        fields = [
            "id",
            "code",
            "name",
            "type",
            "address",
            "phone",
            "settings",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at"]
        # unique tekshiruvi validate_code da (katta harfga o'tkazib, o'zbekcha xabar bilan)
        extra_kwargs = {"code": {"validators": []}}

    def validate_code(self, value):
        value = value.strip().upper()
        if not value.isalnum():
            raise serializers.ValidationError(
                "Kod faqat harf va raqamlardan iborat bo'lsin", code="invalid"
            )
        qs = Branch.objects.filter(code=value)
        if self.instance is not None:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("Bu kod band", code="unique")
        return value
