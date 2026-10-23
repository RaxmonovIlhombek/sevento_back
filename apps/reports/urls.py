from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
# "reports/jobs/" — "reports/{key}/" dan oldin
router.register("reports/jobs", views.ReportJobViewSet, basename="report-job")
router.register("reports", views.ReportViewSet, basename="report")

urlpatterns = router.urls
