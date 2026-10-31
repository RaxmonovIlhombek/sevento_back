from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("manufacturing/boms", views.BillOfMaterialsViewSet, basename="bom")
router.register("manufacturing/orders", views.ProductionOrderViewSet, basename="production-order")

urlpatterns = router.urls
