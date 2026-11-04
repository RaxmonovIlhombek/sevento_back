from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import viewsets
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.permissions import IsAuthenticated

from core.api.permissions import HasCapability, crud_capability_map

from .filters import DepartmentFilter, EmployeeFilter, PositionFilter
from .models import Department, Employee, Position
from .serializers import DepartmentSerializer, EmployeeSerializer, PositionSerializer


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


class EmployeeViewSet(viewsets.ModelViewSet):
    capability_map = crud_capability_map("hr.view", "hr.manage")
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
