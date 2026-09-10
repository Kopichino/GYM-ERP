from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import (
    AvailabilityViewSet,
    PTSessionViewSet,
    TrainerSlotsView,
    UnavailableViewSet,
)

router = DefaultRouter()
router.register("availability", AvailabilityViewSet, basename="pt-availability")
router.register("unavailable", UnavailableViewSet, basename="pt-unavailable")
router.register("sessions", PTSessionViewSet, basename="pt-session")

urlpatterns = [
    path("slots/", TrainerSlotsView.as_view(), name="pt-slots"),
] + router.urls
