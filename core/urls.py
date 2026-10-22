from django.urls import path

from . import views

urlpatterns = [
    path("health/", views.HealthView.as_view(), name="health"),
    path("settings/", views.SettingListView.as_view(), name="settings-list"),
    path("settings/<str:key>/", views.SettingDetailView.as_view(), name="settings-detail"),
]
