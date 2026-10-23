from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("payments/methods", views.PaymentMethodViewSet, basename="payment-method")
router.register("payments/cash-categories", views.CashFlowCategoryViewSet, basename="cash-category")
router.register("payments/cashboxes", views.CashboxViewSet, basename="cashbox")
router.register(
    "payments/cash-transactions", views.CashTransactionViewSet, basename="cash-transaction"
)

router.register("payments/customers", views.CustomerViewSet, basename="customer")
router.register("payments/debts", views.DebtViewSet, basename="debt")
router.register("payments/payments", views.PaymentViewSet, basename="payment")
router.register("payments/shifts", views.CashShiftViewSet, basename="cash-shift")

urlpatterns = router.urls
