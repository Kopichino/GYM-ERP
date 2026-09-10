from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import BodyMeasurementViewSet, BodyStatsSummaryView, MemberGoalViewSet

router = DefaultRouter()
router.register("measurements", BodyMeasurementViewSet, basename="body-measurement")
router.register("goals", MemberGoalViewSet, basename="member-goal")

urlpatterns = [
    path("summary/", BodyStatsSummaryView.as_view(), name="bodystats-summary"),
] + router.urls
