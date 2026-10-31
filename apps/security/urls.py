from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("security/2fa", views.SecurityViewSet, basename="security-2fa")

urlpatterns = router.urls
