from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .filters import AccountFilter, JournalEntryFilter
from .models import Account, FiscalPeriod, FiscalYear, JournalEntry
from .selectors import trial_balance
from .serializers import (
    AccountSerializer,
    FiscalPeriodSerializer,
    FiscalYearSerializer,
    JournalEntrySerializer,
)
from .services import post_entry, reverse_entry


class AccountViewSet(viewsets.ModelViewSet):
    queryset = Account.objects.all()
    serializer_class = AccountSerializer
    permission_classes = [IsAuthenticated]
    filterset_class = AccountFilter
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    search_fields = ["code", "name"]
    ordering_fields = ["code", "name", "account_type"]
    ordering = ["code"]


class FiscalYearViewSet(viewsets.ModelViewSet):
    queryset = FiscalYear.objects.all()
    serializer_class = FiscalYearSerializer
    permission_classes = [IsAuthenticated]
    ordering = ["-year"]


class FiscalPeriodViewSet(viewsets.ModelViewSet):
    queryset = FiscalPeriod.objects.select_related("fiscal_year").all()
    serializer_class = FiscalPeriodSerializer
    permission_classes = [IsAuthenticated]
    ordering = ["fiscal_year__year", "number"]


class JournalEntryViewSet(viewsets.ModelViewSet):
    queryset = JournalEntry.objects.select_related("fiscal_period", "branch", "created_by").prefetch_related("lines__account")
    serializer_class = JournalEntrySerializer
    permission_classes = [IsAuthenticated]
    filterset_class = JournalEntryFilter
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    search_fields = ["number", "description"]
    ordering_fields = ["date", "number", "status"]
    ordering = ["-date", "-id"]

    @action(detail=True, methods=["post"])
    def post(self, request, pk=None):
        entry = self.get_object()
        try:
            post_entry(entry=entry, user=request.user)
        except ValueError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(self.get_serializer(entry).data)

    @action(detail=True, methods=["post"])
    def reverse(self, request, pk=None):
        entry = self.get_object()
        date = request.data.get("date")
        description = request.data.get("description")
        try:
            new_entry = reverse_entry(entry=entry, user=request.user, date=date, description=description)
        except ValueError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(self.get_serializer(new_entry).data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=["get"])
    def trial_balance(self, request):
        fp_id = request.query_params.get("fiscal_period")
        branch_id = request.query_params.get("branch")
        date_to = request.query_params.get("date_to")
        fp = FiscalPeriod.objects.get(pk=fp_id) if fp_id else None
        from apps.branches.models import Branch

        branch = Branch.objects.get(pk=branch_id) if branch_id else None
        rows = trial_balance(fiscal_period=fp, branch=branch, date_to=date_to)
        data = [
            {
                "account": r["account"].code,
                "name": r["account"].name,
                "type": r["account"].account_type,
                "debit": str(r["debit"]),
                "credit": str(r["credit"]),
                "balance": str(r["balance"]),
            }
            for r in rows
        ]
        return Response(data)
