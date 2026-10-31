from rest_framework import serializers

from .models import PayrollRun, Payslip


class PayslipSerializer(serializers.ModelSerializer):
    employee_number = serializers.CharField(source="employee.employee_number", read_only=True)
    employee_name = serializers.CharField(source="employee.user.full_name", read_only=True)

    class Meta:
        model = Payslip
        fields = [
            "id",
            "run",
            "employee",
            "employee_number",
            "employee_name",
            "base_salary",
            "bonus",
            "allowance",
            "deduction",
            "tax",
            "gross",
            "net",
            "notes",
            "created_at",
            "updated_at",
        ]


class PayrollRunSerializer(serializers.ModelSerializer):
    branch_name = serializers.CharField(source="branch.name", read_only=True)
    payslips = PayslipSerializer(many=True, read_only=True)

    class Meta:
        model = PayrollRun
        fields = [
            "id",
            "period_start",
            "period_end",
            "branch",
            "branch_name",
            "status",
            "total_gross",
            "total_net",
            "created_by",
            "paid_at",
            "payslips",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["status", "total_gross", "total_net", "created_by", "paid_at"]
