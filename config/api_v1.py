"""Barcha app URL lari /api/v1/ ostida shu yerda yig'iladi."""

from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

urlpatterns = [
    path("schema/", SpectacularAPIView.as_view(), name="schema"),
    path("docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="docs"),
    path("", include("core.urls")),
    path("", include("apps.accounts.urls")),
    path("", include("apps.branches.urls")),
    path("", include("apps.audit.urls")),
    path("", include("apps.realtime.urls")),
    path("", include("apps.currency.urls")),
    path("", include("apps.catalog.urls")),
    path("", include("apps.inventory.urls")),
    path("", include("apps.purchasing.urls")),
    path("", include("apps.payments.urls")),
    path("", include("apps.sales.urls")),
    path("", include("apps.reports.urls")),
]
