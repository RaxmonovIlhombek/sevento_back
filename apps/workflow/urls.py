from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("workflow/rules", views.ApprovalRuleViewSet, basename="approval-rule")
router.register("workflow/instances", views.ApprovalInstanceViewSet, basename="approval-instance")

urlpatterns = router.urls
