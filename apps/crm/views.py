from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import viewsets
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.permissions import IsAuthenticated

from .filters import ActivityFilter, DealFilter, LeadFilter
from .models import Activity, Deal, Lead
from .serializers import ActivitySerializer, DealSerializer, LeadSerializer


class LeadViewSet(viewsets.ModelViewSet):
    queryset = Lead.objects.all()
    serializer_class = LeadSerializer
    permission_classes = [IsAuthenticated]
    filterset_class = LeadFilter
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    search_fields = ["name", "company", "phone", "email"]
    ordering = ["-created_at"]


class DealViewSet(viewsets.ModelViewSet):
    queryset = Deal.objects.select_related("lead", "customer", "owner", "branch").all()
    serializer_class = DealSerializer
    permission_classes = [IsAuthenticated]
    filterset_class = DealFilter
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    search_fields = ["name"]
    ordering = ["-created_at"]


class ActivityViewSet(viewsets.ModelViewSet):
    queryset = Activity.objects.select_related("lead", "deal", "owner").all()
    serializer_class = ActivitySerializer
    permission_classes = [IsAuthenticated]
    filterset_class = ActivityFilter
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    search_fields = ["subject"]
    ordering = ["-created_at"]
