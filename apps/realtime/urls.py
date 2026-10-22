from django.urls import path

from . import views

urlpatterns = [
    path("realtime/ticket/", views.TicketView.as_view(), name="realtime-ticket"),
    path("realtime/notice/", views.NoticeView.as_view(), name="realtime-notice"),
]
