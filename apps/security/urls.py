from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("security/2fa", views.SecurityViewSet, basename="security-2fa")
router.register("security/logins", views.LoginEventViewSet, basename="security-login")

urlpatterns = router.urls
