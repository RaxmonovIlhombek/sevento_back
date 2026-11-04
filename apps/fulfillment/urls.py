from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("fulfillment/orders", views.FulfillmentViewSet, basename="fulfillment")

urlpatterns = router.urls
