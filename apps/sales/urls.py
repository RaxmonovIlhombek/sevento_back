from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
# "sales/returns/" — "sales/{pk}/" dan oldin (aks holda pk="returns" deb tushunilardi)
router.register("sales/returns", views.SaleReturnViewSet, basename="sale-return")
router.register("sales", views.SaleViewSet, basename="sale")

urlpatterns = router.urls
