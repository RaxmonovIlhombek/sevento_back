from datetime import date, datetime
from decimal import Decimal

from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from .models import ReportJob
from .registry import CATEGORIES
from .renderers import renderer_formats
from .types import Column


def jsonable(value):
    """Decimal → satr (float emas — pul aniq qolsin), sana → ISO."""
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, datetime | date):
        return value.isoformat()
    return value


class ChoiceSerializer(serializers.Serializer):
    value = serializers.CharField()
    label = serializers.CharField()


class FilterSerializer(serializers.Serializer):
    name = serializers.CharField()
    type = serializers.CharField()
    label = serializers.CharField()
    required = serializers.BooleanField()
    choices = serializers.SerializerMethodField()
    default = serializers.SerializerMethodField()

    @extend_schema_field(ChoiceSerializer(many=True))
    def get_choices(self, f):
        return [{"value": v, "label": label} for v, label in f.choices]

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_default(self, f):
        return None if f.default is None else str(f.default)


class ReportInfoSerializer(serializers.Serializer):
    key = serializers.CharField()
    title = serializers.CharField()
    description = serializers.CharField()
    category = serializers.CharField()
    category_label = serializers.SerializerMethodField()
    filters = FilterSerializer(many=True)
    formats = serializers.SerializerMethodField()
    heavy = serializers.BooleanField()

    def get_category_label(self, report) -> str:
        return CATEGORIES.get(report.category, report.category)

    def get_formats(self, report) -> list[str]:
        return renderer_formats()


class ColumnSerializer(serializers.Serializer):
    key = serializers.CharField()
    label = serializers.CharField()
    type = serializers.CharField()
    decimals = serializers.IntegerField()
    decimals_key = serializers.CharField(allow_null=True)
    total = serializers.BooleanField()


class ReportResultSerializer(serializers.Serializer):
    key = serializers.CharField()
    title = serializers.CharField()
    subtitle = serializers.CharField()
    params = serializers.DictField()
    columns = ColumnSerializer(many=True)
    rows = serializers.SerializerMethodField()
    totals = serializers.SerializerMethodField()
    notes = serializers.ListField(child=serializers.CharField())
    row_count = serializers.IntegerField()
    truncated = serializers.BooleanField()
    heavy = serializers.BooleanField(help_text="Fayl fonda tayyorlanadi (report.ready)")

    @extend_schema_field(serializers.ListField(child=serializers.DictField()))
    def get_rows(self, data):
        columns: list[Column] = data["columns"]
        keys = [c.key for c in columns] + [c.decimals_key for c in columns if c.decimals_key]
        return [{k: jsonable(row.get(k)) for k in keys} for row in data["rows"]]

    @extend_schema_field(serializers.DictField(allow_null=True))
    def get_totals(self, data):
        totals = data["totals"]
        return {k: jsonable(v) for k, v in totals.items()} if totals else None


class ExportRequestSerializer(serializers.Serializer):
    format = serializers.ChoiceField(choices=[("pdf", "PDF"), ("xlsx", "Excel")])
    params = serializers.DictField(required=False, default=dict)


class ReportJobSerializer(serializers.ModelSerializer):
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    download_url = serializers.SerializerMethodField()

    class Meta:
        model = ReportJob
        fields = [
            "id",
            "report_key",
            "title",
            "format",
            "params",
            "status",
            "status_display",
            "rows_count",
            "error",
            "created_at",
            "finished_at",
            "download_url",
        ]
        read_only_fields = fields

    def get_download_url(self, job) -> str | None:
        from .services import download_url

        return download_url(job) if job.status == ReportJob.Status.READY and job.file else None


# --- dashboard ---

MONEY = {"max_digits": 24, "decimal_places": 2}


class KpiSerializer(serializers.Serializer):
    value = serializers.DecimalField(**MONEY)
    previous = serializers.DecimalField(**MONEY)
    change = serializers.DecimalField(
        max_digits=10, decimal_places=1, allow_null=True, help_text="oldingi davrga nisbatan %"
    )


class DashboardKpiSerializer(serializers.Serializer):
    revenue = KpiSerializer()
    profit = KpiSerializer(required=False, help_text="faqat reports.financial bilan")
    sales_count = KpiSerializer()
    average_check = KpiSerializer()
    returns = KpiSerializer()


class PeriodSerializer(serializers.Serializer):
    key = serializers.CharField()
    date_from = serializers.DateField()
    date_to = serializers.DateField()


class SeriesPointSerializer(serializers.Serializer):
    label = serializers.CharField()
    revenue = serializers.DecimalField(**MONEY)
    profit = serializers.DecimalField(**MONEY, required=False)
    count = serializers.IntegerField()


class BranchSalesSerializer(serializers.Serializer):
    branch = serializers.CharField()
    revenue = serializers.DecimalField(**MONEY)
    count = serializers.IntegerField()


class TopProductSerializer(serializers.Serializer):
    product_id = serializers.IntegerField()
    name = serializers.CharField()
    unit = serializers.CharField()
    quantity = serializers.DecimalField(max_digits=14, decimal_places=3)
    revenue = serializers.DecimalField(**MONEY)


class MethodShareSerializer(serializers.Serializer):
    method = serializers.CharField()
    amount = serializers.DecimalField(**MONEY)


class CashBalanceSerializer(serializers.Serializer):
    currency = serializers.CharField()
    decimal_places = serializers.IntegerField()
    balance = serializers.DecimalField(max_digits=24, decimal_places=4)


class DebtTotalsSerializer(serializers.Serializer):
    open = serializers.DecimalField(**MONEY)
    overdue = serializers.DecimalField(**MONEY)
    overdue_count = serializers.IntegerField()


class InventoryTotalsSerializer(serializers.Serializer):
    low_stock = serializers.IntegerField()
    stock_value = serializers.DecimalField(**MONEY, allow_null=True)
    incoming_transfers = serializers.IntegerField()


class DashboardSerializer(serializers.Serializer):
    period = PeriodSerializer()
    base_currency = serializers.CharField()
    show_profit = serializers.BooleanField()
    kpi = DashboardKpiSerializer()
    series = SeriesPointSerializer(many=True)
    by_branch = BranchSalesSerializer(many=True)
    top_products = TopProductSerializer(many=True)
    payment_methods = MethodShareSerializer(many=True)
    cash = CashBalanceSerializer(many=True)
    debts = DebtTotalsSerializer()
    inventory = InventoryTotalsSerializer()


class DashboardQuerySerializer(serializers.Serializer):
    period = serializers.ChoiceField(
        choices=[("today", "Bugun"), ("7d", "7 kun"), ("30d", "30 kun"), ("month", "Shu oy")],
        default="today",
    )
    branch = serializers.IntegerField(required=False, allow_null=True)
