from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("inventory/stock", views.StockViewSet, basename="stock")
router.register("inventory/batches", views.BatchViewSet, basename="batch")
router.register("inventory/movements", views.MovementViewSet, basename="movement")
router.register("inventory/transfers", views.TransferViewSet, basename="transfer")
router.register("inventory/counts", views.StockCountViewSet, basename="stock-count")
router.register(
    r"inventory/counts/(?P<count_pk>\d+)/items",
    views.StockCountItemViewSet,
    basename="stock-count-item",
)
router.register(
    "inventory/write-off-reasons", views.WriteOffReasonViewSet, basename="write-off-reason"
)
router.register("inventory/write-offs", views.WriteOffViewSet, basename="write-off")

urlpatterns = router.urls
