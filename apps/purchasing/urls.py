from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("purchasing/suppliers", views.SupplierViewSet, basename="supplier")
router.register("purchasing/expense-types", views.ExpenseTypeViewSet, basename="expense-type")
router.register("purchasing/purchases", views.PurchaseViewSet, basename="purchase")

urlpatterns = router.urls
