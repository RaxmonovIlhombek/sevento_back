from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("catalog/categories", views.CategoryViewSet, basename="category")
router.register("catalog/units", views.UnitViewSet, basename="unit")
router.register("catalog/price-types", views.PriceTypeViewSet, basename="price-type")
router.register("catalog/products", views.ProductViewSet, basename="product")

urlpatterns = router.urls
