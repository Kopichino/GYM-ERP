from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import AtRiskView, EnquiryViewSet, RetentionPolicyViewSet

router = DefaultRouter()
router.register("enquiries", EnquiryViewSet, basename="enquiry")
router.register("retention", RetentionPolicyViewSet, basename="retentionpolicy")

urlpatterns = [
    path("at-risk/", AtRiskView.as_view(), name="at-risk"),
] + router.urls
