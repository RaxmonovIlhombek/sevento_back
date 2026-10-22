from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import Role, User, UserBranch


class UserBranchInline(admin.TabularInline):
    model = UserBranch
    extra = 0


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ("username", "full_name", "role", "is_active", "is_superuser", "last_login")
    list_filter = ("role", "is_active", "is_superuser")
    search_fields = ("username", "full_name", "phone")
    ordering = ("full_name",)
    inlines = [UserBranchInline]
    fieldsets = (
        (None, {"fields": ("username", "password")}),
        ("Shaxsiy", {"fields": ("full_name", "phone", "email")}),
        ("Huquqlar", {"fields": ("role", "is_active", "is_staff", "is_superuser")}),
        ("Sanalar", {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("username", "full_name", "role", "password1", "password2"),
            },
        ),
    )


@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "is_system", "updated_at")
    readonly_fields = ("is_system",)
