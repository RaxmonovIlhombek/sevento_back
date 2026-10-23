from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("payments/methods", views.PaymentMethodViewSet, basename="payment-method")
router.register("payments/cash-categories", views.CashFlowCategoryViewSet, basename="cash-category")
router.register("payments/cashboxes", views.CashboxViewSet, basename="cashbox")
router.register(
    "payments/cash-transactions", views.CashTransactionViewSet, basename="cash-transaction"
)

urlpatterns = router.urls
