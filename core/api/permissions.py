from rest_framework.permissions import BasePermission


class HasCapability(BasePermission):
    """View dagi `capability_map` (ViewSet: action → huquq) yoki `required_capability` bo'yicha.

    capability_map da bo'lmagan action — rad etiladi (xavfsiz default); "*" kaliti hammasi uchun.
    Qiymat tuple bo'lsa — ulardan **birortasi** yetarli (masalan POS uchun to'lov turlari ro'yxati).
    """

    message = "Ruxsat yo'q"

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        required = self.required_capability(request, view)
        if required is None:
            return True
        if required is False:
            return False
        if isinstance(required, tuple | list | frozenset):
            return any(user.has_capability(code) for code in required)
        return user.has_capability(required)

    @staticmethod
    def required_capability(request, view):
        capability_map = getattr(view, "capability_map", None)
        if capability_map is not None:
            action = getattr(view, "action", None)
            if action is None and hasattr(view, "action_map"):
                return None  # ViewSet da bu metod marshrutlanmagan → DRF 405 qaytaradi
            action = action or request.method.lower()
            if action in capability_map:
                return capability_map[action]
            if action == "partial_update" and "update" in capability_map:
                return capability_map["update"]
            if "*" in capability_map:
                return capability_map["*"]
            return False
        return getattr(view, "required_capability", None)


def capability_required(code: str) -> type[BasePermission]:
    """APIView uchun: permission_classes = [IsAuthenticated, capability_required("audit.view")]."""

    class _Permission(HasCapability):
        def required_capability(self, request, view):
            return code

    _Permission.__name__ = f"Capability_{code.replace('.', '_')}"
    return _Permission
