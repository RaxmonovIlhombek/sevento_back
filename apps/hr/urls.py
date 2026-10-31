from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("hr/departments", views.DepartmentViewSet, basename="department")
router.register("hr/positions", views.PositionViewSet, basename="position")
router.register("hr/employees", views.EmployeeViewSet, basename="employee")

urlpatterns = router.urls
