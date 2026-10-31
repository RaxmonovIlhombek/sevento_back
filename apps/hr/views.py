from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import viewsets
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.permissions import IsAuthenticated

from .filters import DepartmentFilter, EmployeeFilter, PositionFilter
from .models import Department, Employee, Position
from .serializers import DepartmentSerializer, EmployeeSerializer, PositionSerializer


class DepartmentViewSet(viewsets.ModelViewSet):
    queryset = Department.objects.all()
    serializer_class = DepartmentSerializer
    permission_classes = [IsAuthenticated]
    filterset_class = DepartmentFilter
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    search_fields = ["name"]
    ordering = ["name"]


class PositionViewSet(viewsets.ModelViewSet):
    queryset = Position.objects.select_related("department").all()
    serializer_class = PositionSerializer
    permission_classes = [IsAuthenticated]
    filterset_class = PositionFilter
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    search_fields = ["name"]
    ordering = ["name"]


class EmployeeViewSet(viewsets.ModelViewSet):
    queryset = Employee.objects.select_related("user", "department", "position", "branch").all()
    serializer_class = EmployeeSerializer
    permission_classes = [IsAuthenticated]
    filterset_class = EmployeeFilter
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    search_fields = ["employee_number", "user__username", "user__full_name"]
    ordering = ["employee_number"]
