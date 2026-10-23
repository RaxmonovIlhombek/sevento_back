from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("inventory/stock", views.StockViewSet, basename="stock")
router.register("inventory/batches", views.BatchViewSet, basename="batch")
router.register("inventory/movements", views.MovementViewSet, basename="movement")

urlpatterns = router.urls
