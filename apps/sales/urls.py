from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("sales", views.SaleViewSet, basename="sale")

urlpatterns = router.urls
