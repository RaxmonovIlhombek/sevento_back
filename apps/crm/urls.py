from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("crm/leads", views.LeadViewSet, basename="lead")
router.register("crm/deals", views.DealViewSet, basename="deal")
router.register("crm/activities", views.ActivityViewSet, basename="activity")

urlpatterns = router.urls
