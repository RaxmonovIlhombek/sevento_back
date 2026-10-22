from drf_spectacular.utils import extend_schema
from rest_framework import mixins, viewsets

from core.api.mixins import BranchScopedQuerySetMixin, CapabilityViewSetMixin

from . import selectors, services
from .models import Branch
from .serializers import BranchSerializer


@extend_schema(tags=["branches"])
class BranchViewSet(
    CapabilityViewSetMixin,
    BranchScopedQuerySetMixin,
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    mixins.ListModelMixin,
    viewsets.GenericViewSet,
):
    """Nuqtalar: ro'yxat — har kim o'zi ko'ra oladiganlarini; o'zgartirish — branches.manage."""

    queryset = Branch.objects.all()
    serializer_class = BranchSerializer
    branch_field = "pk"
    capability_map = {
        "list": None,
        "retrieve": None,
        "create": "branches.manage",
        "update": "branches.manage",
    }
    filterset_fields = ["type", "is_active"]
    search_fields = ["code", "name", "address"]
    ordering_fields = ["name", "code", "created_at"]
    ordering = ["name"]

    def get_queryset(self):
        return selectors.branches_for_user(self.request.user)

    def perform_create(self, serializer):
        serializer.instance = services.create_branch(
            actor=self.request.user, **serializer.validated_data
        )

    def perform_update(self, serializer):
        serializer.instance = services.update_branch(
            actor=self.request.user, branch=serializer.instance, **serializer.validated_data
        )
