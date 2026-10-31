from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("accounting/accounts", views.AccountViewSet, basename="account")
router.register("accounting/fiscal-years", views.FiscalYearViewSet, basename="fiscal-year")
router.register("accounting/fiscal-periods", views.FiscalPeriodViewSet, basename="fiscal-period")
router.register("accounting/journal-entries", views.JournalEntryViewSet, basename="journal-entry")

urlpatterns = router.urls
