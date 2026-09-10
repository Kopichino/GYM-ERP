from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import (
    AccessRequestView,
    DeviceEventListView,
    DeviceEventReprocessView,
    DeviceViewSet,
    PunchIngestView,
)

router = DefaultRouter()
router.register("", DeviceViewSet, basename="device")

urlpatterns = [
    # Device-authenticated ingest comes first so it isn't shadowed by the
    # router's detail route.
    path("access/", AccessRequestView.as_view(), name="device-access"),
    path("events/ingest/", PunchIngestView.as_view(), name="device-ingest"),
    path("events/", DeviceEventListView.as_view(), name="device-events"),
    path("events/<int:pk>/reprocess/", DeviceEventReprocessView.as_view(), name="device-event-reprocess"),
] + router.urls
