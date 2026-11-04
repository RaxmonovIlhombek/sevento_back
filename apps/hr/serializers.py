from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

from apps.accounts.models import Role, User
from apps.branches.models import Branch

from .models import Department, Employee, Position


class DepartmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Department
        fields = ["id", "name", "parent", "branch", "is_active", "created_at", "updated_at"]


class PositionSerializer(serializers.ModelSerializer):
    department_name = serializers.CharField(source="department.name", read_only=True)

    class Meta:
        model = Position
        fields = [
            "id",
            "name",
            "department",
            "department_name",
            "is_active",
            "created_at",
            "updated_at",
        ]


class EmployeeSerializer(serializers.ModelSerializer):
    user_username = serializers.CharField(source="user.username", read_only=True)
    user_full_name = serializers.CharField(source="user.full_name", read_only=True)
    department_name = serializers.CharField(source="department.name", read_only=True)
    position_name = serializers.CharField(source="position.name", read_only=True)
    branch_name = serializers.CharField(source="branch.name", read_only=True)

    class Meta:
        model = Employee
        fields = [
            "id",
            "user",
            "user_username",
            "user_full_name",
            "employee_number",
            "department",
            "department_name",
            "position",
            "position_name",
            "branch",
            "branch_name",
            "hire_date",
            "termination_date",
            "status",
            "base_salary",
            "phone",
            "address",
            "notes",
            "created_at",
            "updated_at",
        ]


class EmployeeSerializerScoped(EmployeeSerializer):
    """Tahrirlashda yangi nuqta foydalanuvchi doirasida bo'lishi shart."""

    def validate_branch(self, branch):
        request = self.context.get("request")
        ids = request.user.accessible_branch_ids() if request else None
        if ids is not None and branch.pk not in ids:
            raise serializers.ValidationError("Bu nuqta uchun ruxsat yo'q")
        return branch


class HireSerializer(serializers.Serializer):
    """Yangi xodim: login + rol + nuqta + ish joyi bitta formada."""

    full_name = serializers.CharField(max_length=150)
    username = serializers.CharField(max_length=150)
    password = serializers.CharField(write_only=True, min_length=8, max_length=128)
    phone = serializers.CharField(max_length=30, required=False, allow_blank=True, default="")
    role = serializers.PrimaryKeyRelatedField(queryset=Role.objects.all())
    branch = serializers.PrimaryKeyRelatedField(queryset=Branch.objects.filter(is_active=True))
    department = serializers.PrimaryKeyRelatedField(queryset=Department.objects.all())
    position = serializers.PrimaryKeyRelatedField(queryset=Position.objects.all())
    employee_number = serializers.CharField(
        max_length=40, required=False, allow_blank=True, default=""
    )
    hire_date = serializers.DateField(required=False)
    base_salary = serializers.DecimalField(
        max_digits=20, decimal_places=4, min_value=0, required=False, default=0
    )
    address = serializers.CharField(required=False, allow_blank=True, default="")
    notes = serializers.CharField(required=False, allow_blank=True, default="")

    def validate_username(self, value):
        if User.objects.filter(username__iexact=value).exists():
            raise serializers.ValidationError("Bu login band")
        return value

    def validate_employee_number(self, value):
        if value and Employee.objects.filter(employee_number=value).exists():
            raise serializers.ValidationError("Bu xodim raqami band")
        return value

    def validate(self, attrs):
        validate_password(attrs["password"])
        return attrs


class _OptionSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()


class _RoleOptionSerializer(_OptionSerializer):
    code = serializers.CharField()


class _BranchOptionSerializer(_OptionSerializer):
    code = serializers.CharField()


class _PositionOptionSerializer(_OptionSerializer):
    department = serializers.IntegerField()


class HireOptionsSerializer(serializers.Serializer):
    """Yollash formasi uchun: foydalanuvchi o'zi tanlay oladigan qiymatlar."""

    roles = _RoleOptionSerializer(many=True)
    branches = _BranchOptionSerializer(many=True)
    departments = _OptionSerializer(many=True)
    positions = _PositionOptionSerializer(many=True)


class TerminateSerializer(serializers.Serializer):
    termination_date = serializers.DateField(required=False)
