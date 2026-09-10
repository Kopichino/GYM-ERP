from rest_framework.routers import DefaultRouter

from django.urls import path

from .views import (
    DomainViewSet,
    LeadApiKeyViewSet,
    PublicLeadView,
    SendingDomainViewSet,
)

router = DefaultRouter()
router.register("domains", DomainViewSet, basename="domain")
router.register("sending-domain", SendingDomainViewSet, basename="sending-domain")
router.register("lead-keys", LeadApiKeyViewSet, basename="lead-key")

urlpatterns = [
    # Public: a gym's website posts here with its lead key.
    path("leads/", PublicLeadView.as_view(), name="public-lead"),
] + router.urls
