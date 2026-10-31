from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.filters import OrderingFilter
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .filters import PayrollRunFilter
from .models import PayrollRun, Payslip
from .serializers import PayrollRunSerializer


class PayrollRunViewSet(viewsets.ModelViewSet):
    queryset = PayrollRun.objects.select_related("branch", "created_by").prefetch_related("payslips__employee").all()
    serializer_class = PayrollRunSerializer
    permission_classes = [IsAuthenticated]
    filterset_class = PayrollRunFilter
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    ordering = ["-period_end"]

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    @action(detail=True, methods=["post"])
    def calculate(self, request, pk=None):
        run = self.get_object()
        if run.status != PayrollRun.Status.DRAFT:
            return Response({"detail": "Faqat qoralamani hisoblash mumkin"}, status=400)
        from apps.hr.models import Employee

        employees = Employee.objects.filter(branch=run.branch, status=Employee.Status.ACTIVE)
        run.payslips.all().delete()
        total_gross = 0
        total_net = 0
        for emp in employees:
            gross = emp.base_salary
            tax = gross * 0  # soliq logikasi keyinroq
            net = gross - tax
            Payslip.objects.create(
                run=run, employee=emp, base_salary=emp.base_salary, gross=gross, net=net, tax=tax
            )
            total_gross += gross
            total_net += net
        run.total_gross = total_gross
        run.total_net = total_net
        run.status = PayrollRun.Status.CALCULATED
        run.save(update_fields=["total_gross", "total_net", "status", "updated_at"])
        return Response(self.get_serializer(run).data)

    @action(detail=True, methods=["post"])
    def pay(self, request, pk=None):
        run = self.get_object()
        if run.status != PayrollRun.Status.CALCULATED:
            return Response({"detail": "Avval hisoblash kerak"}, status=400)
        from django.utils import timezone

        run.status = PayrollRun.Status.PAID
        run.paid_at = timezone.now()
        run.save(update_fields=["status", "paid_at", "updated_at"])
        return Response(self.get_serializer(run).data)
