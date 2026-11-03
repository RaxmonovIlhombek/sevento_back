from django.contrib import admin

from .models import LoginEvent, TwoFactorDevice

admin.site.register(TwoFactorDevice)


@admin.register(LoginEvent)
class LoginEventAdmin(admin.ModelAdmin):
    list_display = ("created_at", "username", "success", "ip", "browser", "os", "device_type")
    list_filter = ("success", "device_type")
    search_fields = ("username", "ip")
    readonly_fields = [f.name for f in LoginEvent._meta.fields]
