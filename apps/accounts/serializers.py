from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.branches import selectors as branch_selectors

from .capabilities import validate_codes
from .models import Role, User


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=150)
    password = serializers.CharField(write_only=True, trim_whitespace=False)


class RoleBriefSerializer(serializers.Serializer):
    code = serializers.CharField()
    name = serializers.CharField()


class UserBranchSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    code = serializers.CharField()
    name = serializers.CharField()
    type = serializers.CharField()
    is_default = serializers.BooleanField()


class MeSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    username = serializers.CharField()
    full_name = serializers.CharField()
    phone = serializers.CharField()
    is_superuser = serializers.BooleanField()
    role = RoleBriefSerializer(allow_null=True)
    capabilities = serializers.ListField(child=serializers.CharField())
    branches = UserBranchSerializer(many=True)
    all_branches = serializers.BooleanField()


class LoginResponseSerializer(serializers.Serializer):
    access = serializers.CharField()
    user = MeSerializer()


class RefreshResponseSerializer(serializers.Serializer):
    access = serializers.CharField()


class ChangePasswordSerializer(serializers.Serializer):
    current_password = serializers.CharField(write_only=True, trim_whitespace=False)
    new_password = serializers.CharField(write_only=True, trim_whitespace=False)

    def validate_current_password(self, value):
        if not self.context["request"].user.check_password(value):
            raise serializers.ValidationError("Joriy parol noto'g'ri", code="invalid_password")
        return value

    def validate_new_password(self, value):
        return _validate_password(value)


class CapabilitySerializer(serializers.Serializer):
    code = serializers.CharField()
    name = serializers.CharField()
    group = serializers.CharField()


class RoleSerializer(serializers.ModelSerializer):
    users_count = serializers.IntegerField(read_only=True)
    capabilities = serializers.ListField(
        child=serializers.CharField(), required=False, default=list
    )

    class Meta:
        model = Role
        fields = [
            "id",
            "code",
            "name",
            "capabilities",
            "is_system",
            "users_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["is_system", "created_at", "updated_at"]
        extra_kwargs = {"code": {"validators": []}}

    def validate_code(self, value):
        qs = Role.objects.filter(code=value)
        if self.instance is not None:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("Bu kod band", code="unique")
        return value

    def validate_capabilities(self, value):
        unknown = validate_codes(value)
        if unknown:
            raise serializers.ValidationError(
                f"Noma'lum huquqlar: {', '.join(unknown)}", code="unknown_capability"
            )
        return sorted(set(value))


class UserBranchLinkSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    code = serializers.CharField()
    name = serializers.CharField()
    is_default = serializers.BooleanField()


class UserSerializer(serializers.ModelSerializer):
    role_detail = RoleBriefSerializer(source="role", read_only=True)
    branches = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "full_name",
            "phone",
            "role",
            "role_detail",
            "branches",
            "is_active",
            "is_superuser",
            "last_login",
            "date_joined",
        ]
        read_only_fields = fields

    @extend_schema_field(UserBranchLinkSerializer(many=True))
    def get_branches(self, user) -> list[dict]:
        return [
            {
                "id": link.branch.id,
                "code": link.branch.code,
                "name": link.branch.name,
                "is_default": link.is_default,
            }
            for link in user.branch_links.all()
        ]


class UserWriteSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=150)
    password = serializers.CharField(write_only=True, required=False, trim_whitespace=False)
    full_name = serializers.CharField(max_length=150)
    phone = serializers.CharField(max_length=30, required=False, allow_blank=True, default="")
    role = serializers.PrimaryKeyRelatedField(queryset=Role.objects.all(), allow_null=True)
    branch_ids = serializers.PrimaryKeyRelatedField(
        queryset=branch_selectors.all_branches(), many=True, required=False
    )
    default_branch_id = serializers.IntegerField(required=False, allow_null=True)
    is_active = serializers.BooleanField(required=False, default=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance is None:
            self.fields["password"].required = True

    def validate_username(self, value):
        qs = User.objects.filter(username__iexact=value)
        if self.instance is not None:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("Bu login band", code="unique")
        return value

    def validate_password(self, value):
        return _validate_password(value)

    def validate(self, attrs):
        branches = attrs.get("branch_ids")
        default_id = attrs.get("default_branch_id")
        if default_id is not None:
            ids = {b.pk for b in branches} if branches is not None else set()
            if default_id not in ids:
                raise serializers.ValidationError(
                    {
                        "default_branch_id": [
                            "Asosiy nuqta biriktirilgan nuqtalar ichida bo'lishi kerak"
                        ]
                    }
                )
        if branches is not None:
            attrs["branch_ids"] = [b.pk for b in branches]
        return attrs


class SetPasswordSerializer(serializers.Serializer):
    new_password = serializers.CharField(write_only=True, trim_whitespace=False)

    def validate_new_password(self, value):
        return _validate_password(value)


def _validate_password(value: str) -> str:
    try:
        validate_password(value)
    except DjangoValidationError as exc:
        raise serializers.ValidationError(list(exc.messages), code="password_too_weak") from None
    return value
