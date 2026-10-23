from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("currencies", views.CurrencyViewSet, basename="currency")
router.register("currency-rates", views.ExchangeRateViewSet, basename="currency-rate")

urlpatterns = router.urls
