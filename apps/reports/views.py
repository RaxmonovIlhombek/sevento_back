from django.http import FileResponse, HttpResponse
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from core.access import ensure_branch_access
from core.api.mixins import CapabilityViewSetMixin
from core.api.schema import ERROR_RESPONSE
from core.exceptions import BusinessRuleError

from . import services
from .dashboard import build_dashboard
from .models import ReportJob
from .registry import reports_for
from .serializers import (
    DashboardQuerySerializer,
    DashboardSerializer,
    ExportRequestSerializer,
    ReportInfoSerializer,
    ReportJobSerializer,
    ReportResultSerializer,
)

ANY_REPORTS = ("reports.view", "reports.financial")


@extend_schema(tags=["reports"])
class ReportViewSet(CapabilityViewSetMixin, viewsets.ViewSet):
    """Hisobotlar reyestri. Ko'rish — JSON (ekranda); fayl — PDF/Excel.

    Har hisobotning o'z huquqi bor (`reports.view` / `reports.financial`); nuqta chegarasi
    selectorlarda qo'llanadi. Parametrlar — hisobot `filters` ro'yxatidagi nomlar.
    """

    capability_map = {
        "list": ANY_REPORTS,
        "retrieve": ANY_REPORTS,
        "export": ANY_REPORTS,
        "dashboard": "dashboard.view",
    }
    lookup_field = "key"
    lookup_value_regex = "[a-z0-9_]+"

    @extend_schema(responses=ReportInfoSerializer(many=True))
    def list(self, request):
        return Response(ReportInfoSerializer(reports_for(request.user), many=True).data)

    @extend_schema(
        parameters=[
            OpenApiParameter(
                "params",
                OpenApiTypes.OBJECT,
                style="form",
                explode=True,
                description="hisobot filtrlari (date_from, date_to, branch, ...)",
            )
        ],
        responses={200: ReportResultSerializer, 400: ERROR_RESPONSE, 403: ERROR_RESPONSE},
    )
    def retrieve(self, request, key=None):
        data = services.preview(user=request.user, key=key, data=request.query_params)
        return Response(ReportResultSerializer(data).data)

    @extend_schema(parameters=[DashboardQuerySerializer], responses=DashboardSerializer)
    @action(detail=False, methods=["get"])
    def dashboard(self, request):
        """Rahbar dashboardi: KPI (oldingi davr bilan), kunlik/soatlik qator, nuqtalar, top tovar.

        Jonli: `dashboard.updated` kelganda frontend qayta so'raydi.
        """
        query = DashboardQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        branch_id = query.validated_data.get("branch")
        if branch_id:
            ensure_branch_access(request.user, branch_id)
        data = build_dashboard(
            request.user, period=query.validated_data["period"], branch_id=branch_id
        )
        return Response(DashboardSerializer(data).data)

    @extend_schema(
        request=ExportRequestSerializer,
        responses={
            (200, "application/pdf"): OpenApiTypes.BINARY,
            (
                200,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            ): OpenApiTypes.BINARY,
            202: OpenApiResponse(ReportJobSerializer, description="fonda tayyorlanadi"),
            400: ERROR_RESPONSE,
        },
    )
    @action(detail=True, methods=["post"])
    def export(self, request, key=None):
        """Yengil hisobot — fayl darhol; og'ir yoki uzun davr — 202 + ReportJob (report.ready)."""
        serializer = ExportRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = services.export(
            user=request.user,
            key=key,
            fmt=serializer.validated_data["format"],
            data=serializer.validated_data["params"],
        )
        if isinstance(result, ReportJob):
            return Response(ReportJobSerializer(result).data, status=status.HTTP_202_ACCEPTED)
        response = HttpResponse(result.content, content_type=result.content_type)
        response["Content-Disposition"] = f'attachment; filename="{result.filename}"'
        return response


@extend_schema(tags=["reports"])
class ReportJobViewSet(
    CapabilityViewSetMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    """Fonda tayyorlangan hisobotlar — faqat o'ziniki (oxirgi 20 ta)."""

    queryset = ReportJob.objects.none()
    serializer_class = ReportJobSerializer
    capability_map = {"list": ANY_REPORTS, "retrieve": ANY_REPORTS, "download": ANY_REPORTS}
    pagination_class = None

    def get_queryset(self):
        return ReportJob.objects.filter(requested_by=self.request.user)

    def list(self, request, *args, **kwargs):
        rows = self.get_queryset()[:20]
        return Response(self.get_serializer(rows, many=True).data)

    @extend_schema(responses={(200, "application/octet-stream"): OpenApiTypes.BINARY})
    @action(detail=True, methods=["get"])
    def download(self, request, pk=None):
        job = self.get_object()
        if job.status != ReportJob.Status.READY or not job.file:
            raise BusinessRuleError("Fayl hali tayyor emas", code="report_not_ready")
        filename = job.file.name.rsplit("/", 1)[-1].split("-", 1)[-1]
        return FileResponse(job.file.open("rb"), as_attachment=True, filename=filename)
