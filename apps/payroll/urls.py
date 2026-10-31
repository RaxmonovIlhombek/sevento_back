from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("payroll/runs", views.PayrollRunViewSet, basename="payroll-run")

urlpatterns = router.urls
