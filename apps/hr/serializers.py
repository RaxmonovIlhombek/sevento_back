from rest_framework import serializers

from .models import Department, Employee, Position


class DepartmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Department
        fields = ["id", "name", "parent", "branch", "is_active", "created_at", "updated_at"]


class PositionSerializer(serializers.ModelSerializer):
    department_name = serializers.CharField(source="department.name", read_only=True)

    class Meta:
        model = Position
        fields = ["id", "name", "department", "department_name", "is_active", "created_at", "updated_at"]


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
