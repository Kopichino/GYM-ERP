from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import ClassSessionViewSet, MyBookingsView

router = DefaultRouter()
router.register("", ClassSessionViewSet, basename="class-session")

urlpatterns = [
    path("my-bookings/", MyBookingsView.as_view(), name="my-bookings"),
] + router.urls
