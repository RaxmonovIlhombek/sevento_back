from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.accounts.capabilities import assignable_role_codes
from apps.accounts.models import Role
from apps.branches.models import Branch
from core.api.permissions import HasCapability, crud_capability_map

from . import services
from .filters import DepartmentFilter, EmployeeFilter, PositionFilter
from .models import Department, Employee, Position
from .serializers import (
    DepartmentSerializer,
    EmployeeSerializer,
    EmployeeSerializerScoped,
    HireOptionsSerializer,
    HireSerializer,
    PositionSerializer,
    TerminateSerializer,
)


class DepartmentViewSet(viewsets.ModelViewSet):
    capability_map = crud_capability_map("hr.view", "hr.manage")
    queryset = Department.objects.all()
    serializer_class = DepartmentSerializer
    permission_classes = [IsAuthenticated, HasCapability]
    filterset_class = DepartmentFilter
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    search_fields = ["name"]
    ordering = ["name"]


class PositionViewSet(viewsets.ModelViewSet):
    capability_map = crud_capability_map("hr.view", "hr.manage")
    queryset = Position.objects.select_related("department").all()
    serializer_class = PositionSerializer
    permission_classes = [IsAuthenticated, HasCapability]
    filterset_class = PositionFilter
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    search_fields = ["name"]
    ordering = ["name"]


STAFF = ("hr.manage", "hr.staff.manage")


class EmployeeViewSet(viewsets.ModelViewSet):
    capability_map = crud_capability_map(
        "hr.view",
        "hr.manage",
        extra={
            "update": STAFF,
            "partial_update": STAFF,
            "hire": STAFF,
            "hire_options": STAFF,
            "terminate": STAFF,
        },
    )
    queryset = Employee.objects.select_related("user", "department", "position", "branch").all()
    serializer_class = EmployeeSerializer
    permission_classes = [IsAuthenticated, HasCapability]
    filterset_class = EmployeeFilter
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    search_fields = ["employee_number", "user__username", "user__full_name"]
    ordering = ["employee_number"]

    def get_queryset(self):
        qs = super().get_queryset()
        branch_ids = self.request.user.accessible_branch_ids()
        # None = barcha nuqtalar; aks holda faqat biriktirilgan nuqtalar xodimlari
        return qs if branch_ids is None else qs.filter(branch_id__in=branch_ids)

    def get_serializer_class(self):
        if self.action in ("update", "partial_update"):
            return EmployeeSerializerScoped
        return EmployeeSerializer

    def perform_update(self, serializer):
        services.check_manageable(self.request.user, serializer.instance)
        serializer.save()

    @extend_schema(responses=HireOptionsSerializer)
    @action(detail=False, methods=["get"], url_path="hire-options", pagination_class=None)
    def hire_options(self, request):
        """Yollash formasi uchun: faqat shu foydalanuvchi tanlay oladigan rol va nuqtalar."""
        user = request.user
        allowed = assignable_role_codes(user)
        roles = Role.objects.order_by("name")
        if allowed is not None:
            roles = roles.filter(code__in=allowed)
        branches = Branch.objects.filter(is_active=True).order_by("name")
        branch_ids = user.accessible_branch_ids()
        if branch_ids is not None:
            branches = branches.filter(pk__in=branch_ids)
        data = {
            "roles": [{"id": r.pk, "code": r.code, "name": r.name} for r in roles],
            "branches": [{"id": b.pk, "code": b.code, "name": b.name} for b in branches],
            "departments": list(
                Department.objects.filter(is_active=True).order_by("name").values("id", "name")
            ),
            "positions": [
                {"id": p.pk, "name": p.name, "department": p.department_id}
                for p in Position.objects.filter(is_active=True).order_by("name")
            ],
        }
        return Response(data)

    @extend_schema(request=HireSerializer, responses={201: EmployeeSerializer})
    @action(detail=False, methods=["post"])
    def hire(self, request):
        """Yangi xodim: login, rol va nuqta bilan birga yaratiladi."""
        serializer = HireSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        employee = services.hire_employee(actor=request.user, **serializer.validated_data)
        return Response(EmployeeSerializer(employee).data, status=status.HTTP_201_CREATED)

    @extend_schema(request=TerminateSerializer, responses=EmployeeSerializer)
    @action(detail=True, methods=["post"])
    def terminate(self, request, pk=None):
        """Ishdan bo'shatish: tizimga kirish ham o'chiriladi."""
        serializer = TerminateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        employee = services.terminate_employee(
            actor=request.user,
            employee=self.get_object(),
            termination_date=serializer.validated_data.get("termination_date"),
        )
        return Response(EmployeeSerializer(employee).data)
