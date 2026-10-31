from django.contrib import admin

from .models import Department, Employee, Position


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ("name", "parent", "branch", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name",)


@admin.register(Position)
class PositionAdmin(admin.ModelAdmin):
    list_display = ("name", "department", "is_active")
    list_filter = ("department", "is_active")
    search_fields = ("name",)


@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = ("employee_number", "user", "department", "position", "status", "hire_date")
    list_filter = ("status", "department", "branch")
    search_fields = ("employee_number", "user__username", "user__full_name")
    readonly_fields = ("created_at", "updated_at")
