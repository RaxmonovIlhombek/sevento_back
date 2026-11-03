from core.api.filters import DateRangeFilterSet

from .models import LoginEvent


class LoginEventFilter(DateRangeFilterSet):
    class Meta:
        model = LoginEvent
        fields = ["user", "success", "device_type"]
