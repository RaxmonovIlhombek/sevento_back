import django_filters

from .models import Department, Employee, Position


class DepartmentFilter(django_filters.FilterSet):
    is_active = django_filters.BooleanFilter()
    branch = django_filters.NumberFilter(field_name="branch_id")
    parent = django_filters.ModelChoiceFilter(queryset=Department.objects.all())

    class Meta:
        model = Department
        fields = ["is_active", "branch", "parent"]


class PositionFilter(django_filters.FilterSet):
    department = django_filters.ModelChoiceFilter(queryset=Department.objects.all())
    is_active = django_filters.BooleanFilter()

    class Meta:
        model = Position
        fields = ["department", "is_active"]


class EmployeeFilter(django_filters.FilterSet):
    department = django_filters.ModelChoiceFilter(queryset=Department.objects.all())
    position = django_filters.ModelChoiceFilter(queryset=Position.objects.all())
    branch = django_filters.NumberFilter(field_name="branch_id")
    status = django_filters.ChoiceFilter(choices=Employee.Status.choices)

    class Meta:
        model = Employee
        fields = ["department", "position", "branch", "status"]
